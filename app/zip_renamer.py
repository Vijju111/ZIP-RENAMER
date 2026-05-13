import os
import shutil
import zipfile
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Tuple

from .utils import (
    PROJECT_LOG_NAME,
    safe_inner_name,
    detect_server_kind,
    extract_date_parts,
    format_date,
    build_output_filename,
    sanitize_server_number,
    sanitize_date_format,
)


@dataclass
class RenameInput:
    exam: str
    city: str
    center: str
    tech: str
    server_number: str      # REQUIRED 01..99 (USER INPUT ONLY)
    date_format: str        # "DD-MM-YYYY" or "MM-DD-YYYY"


@dataclass
class RenameResult:
    processed: int
    skipped: int
    warnings: List[str]


def process_container_zip(
    input_zip_path: str,
    output_zip_path: str,
    meta: RenameInput,
    max_inner_zips: int = 5000,
    chunk_size: int = 1024 * 1024,
) -> RenameResult:
    """
    - processes only inner *.zip files
    - server number is strictly user input (01..99)
    - kind (M/B) from filename text only
    - output zip uses ZIP_STORED (no recompression) and streams copies
    - planning/parsing uses threads
    """
    warnings: List[str] = []
    processed = 0
    skipped = 0

    if not all([meta.exam, meta.city, meta.center, meta.tech]):
        raise ValueError("Missing required fields (Exam, City, Center, Tech).")

    srv_num = sanitize_server_number(meta.server_number)
    date_fmt = sanitize_date_format(meta.date_format)

    with zipfile.ZipFile(input_zip_path, "r") as zin:
        infos = [i for i in zin.infolist() if not i.is_dir()]
        if not infos:
            raise ValueError("ZIP is empty (no files found).")

        # Only inner *.zip
        inner: List[zipfile.ZipInfo] = []
        for info in infos:
            base = safe_inner_name(info.filename)
            if not base:
                skipped += 1
                continue

            low = base.lower()
            if low.startswith(".") or low.startswith("__macosx"):
                skipped += 1
                continue

            if low.endswith(".zip"):
                inner.append(info)
            else:
                skipped += 1

        if not inner:
            raise ValueError("No inner .zip files found inside the container ZIP.")
        if len(inner) > max_inner_zips:
            raise ValueError(f"Too many inner ZIPs ({len(inner)}). Limit is {max_inner_zips}.")

        # Parallel plan computation (threads): parsing + naming only
        src_bases = [safe_inner_name(i.filename) for i in inner]
        max_workers = min(32, (os.cpu_count() or 4))

        def compute(src_base: str) -> Tuple[str, str, List[str]]:
            local_warn: List[str] = []

            # Date
            parts, _note = extract_date_parts(src_base)
            if parts is None:
                date_str = "NO-DATE"
                local_warn.append(f"[{src_base}] date not detected; using NO-DATE")
            else:
                dd, mm, yyyy = parts
                date_str = format_date(dd, mm, yyyy, date_fmt)

            # Kind M/B
            kind, _k = detect_server_kind(src_base)
            if kind is None:
                kind = "U"
                local_warn.append(f"[{src_base}] server type not detected (TCMAIN/TCBACKUP); using U{srv_num}")

            # Server number is ALWAYS user input
            server_code = f"{kind}{srv_num}"

            candidate = build_output_filename(
                exam=meta.exam,
                city=meta.city,
                center=meta.center,
                tech=meta.tech,
                server_code=server_code,
                date_str=date_str,
                suffix=None,
            )
            return src_base, candidate, local_warn

        computed: List[Tuple[str, str, List[str]]] = []
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            for item in ex.map(compute, src_bases):
                computed.append(item)

        # Deduplicate output names
        used_counts: Dict[str, int] = {}
        plan: List[Tuple[zipfile.ZipInfo, str]] = []

        for info, (src_base, candidate, local_warn) in zip(inner, computed):
            warnings.extend(local_warn)
            key = candidate.lower()

            if key in used_counts:
                used_counts[key] += 1
                suffix = used_counts[key]
                final_name = candidate[:-4] + f"_{suffix}.zip" if candidate.lower().endswith(".zip") else (candidate + f"_{suffix}")
                warnings.append(f"[{src_base}] duplicate output name; added suffix _{suffix}")
            else:
                used_counts[key] = 0
                final_name = candidate

            plan.append((info, final_name))

        # Write output ZIP (ZIP_STORED = no recompression) + streaming copy
        with zipfile.ZipFile(output_zip_path, "w", compression=zipfile.ZIP_STORED) as zout:
            report = (
                "ULTRA-FAST ZIP BATCH RENAMER - LOG\n"
                f"Server Number (user input): {srv_num}\n"
                f"Date Format (chosen): {date_fmt}\n"
                f"Processed: {len(plan)} | Skipped(non-zip/hidden): {skipped}\n\n"
            )
            if warnings:
                report += "WARNINGS / NOTES:\n" + "\n".join(warnings) + "\n"
            else:
                report += "No warnings.\n"

            # Log file name as project name
            zout.writestr(PROJECT_LOG_NAME, report)

            for src_info, target_name in plan:
                zi = zipfile.ZipInfo(filename=target_name)
                zi.date_time = src_info.date_time
                zi.external_attr = src_info.external_attr
                zi.compress_type = zipfile.ZIP_STORED

                with zin.open(src_info, "r") as src_f, zout.open(zi, "w") as dst_f:
                    shutil.copyfileobj(src_f, dst_f, length=chunk_size)

                processed += 1

    return RenameResult(processed=processed, skipped=skipped, warnings=warnings)