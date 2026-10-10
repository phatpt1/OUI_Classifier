"""Tra cứu tổ chức đăng ký MAC từ IEEE MA-L/MA-M/MA-S (offline)."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import tempfile
from urllib.request import Request, urlopen

IEEE_FILES = {
    "MA-L": ("oui.csv", "https://standards-oui.ieee.org/oui/oui.csv", 6),
    "MA-M": ("mam.csv", "https://standards-oui.ieee.org/oui28/mam.csv", 7),
    "MA-S": ("oui36.csv", "https://standards-oui.ieee.org/oui36/oui36.csv", 9),
}

MAC_RE = re.compile(
    r"^(?:[0-9A-Fa-f]{12}|[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}|"
    r"[0-9A-Fa-f]{4}(?:\.[0-9A-Fa-f]{4}){2})$"
)


@dataclass(frozen=True)
class VendorMatch:
    vendors: tuple[str, ...]
    prefix: str
    registry: str


class IEEERegistry:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.prefixes: dict[int, dict[str, tuple[str, ...]]] = {6: {}, 7: {}, 9: {}}
        self.counts: dict[str, int] = {}
        self._load()

    def _load(self):
        for registry, (filename, _, bits) in IEEE_FILES.items():
            file_path = self.root / filename
            if not file_path.is_file():
                self.counts[registry] = 0
                continue
            data: dict[str, set[str]] = {}
            with file_path.open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    prefix = re.sub(r"[^0-9A-F]", "", row.get("Assignment", "").upper())
                    vendor = (row.get("Organization Name") or "").strip()
                    kind = (row.get("Registry") or "").strip().upper()
                    if kind == registry and len(prefix) == bits and vendor and re.fullmatch(r"[0-9A-F]+", prefix):
                        data.setdefault(prefix, set()).add(vendor)
            self.prefixes[bits] = {prefix: tuple(sorted(vendors)) for prefix, vendors in data.items()}
            self.counts[registry] = len(data)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def match(self, normalized_mac: str) -> VendorMatch | None:
        for size, kind in ((9, "MA-S"), (7, "MA-M"), (6, "MA-L")):
            prefix = normalized_mac[:size]
            vendors = self.prefixes[size].get(prefix)
            if vendors:
                return VendorMatch(vendors=vendors, prefix=prefix, registry=kind)
        return None


def normalize_mac(raw: object) -> str | None:
    value = str(raw or "").strip()
    if not MAC_RE.fullmatch(value):
        return None
    return re.sub(r"[^0-9A-F]", "", value.upper())


def format_mac(mac: str) -> str:
    return ":".join(mac[index:index + 2] for index in range(0, 12, 2))


def address_status(mac: str) -> str:
    if mac == "FFFFFFFFFFFF":
        return "Broadcast"
    if mac == "000000000000":
        return "Địa chỉ toàn 0"
    first = int(mac[:2], 16)
    if first & 1:
        return "Multicast / nhóm"
    if first & 2:
        return "MAC cục bộ (có thể được ngẫu nhiên hóa)"
    return "MAC toàn cục (unicast)"


def _validate_ieee_csv(payload: bytes, expected_kind: str, prefix_len: int) -> int:
    """Chặn file sai định dạng và nội dung không thuộc đúng registry."""
    import io

    if not payload or len(payload) > 20_000_000:
        raise ValueError(f"File {expected_kind} rỗng hoặc quá lớn (>20 MB).")
    try:
        reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
        if not set(("Registry", "Assignment", "Organization Name")).issubset(reader.fieldnames or []):
            raise ValueError("Thiếu cột chuẩn IEEE.")
        valid = 0
        for row in reader:
            assignment = re.sub(r"[^0-9A-F]", "", (row.get("Assignment") or "").upper())
            if (row.get("Registry") or "").upper() == expected_kind and len(assignment) == prefix_len and row.get("Organization Name"):
                valid += 1
        if valid == 0:
            raise ValueError("Không có bản ghi hợp lệ.")
        return valid
    except UnicodeError as exc:
        raise ValueError("Không đọc được file UTF-8 của IEEE.") from exc


def import_ieee_files(root: Path, uploads: dict[str, bytes], *, update_metadata: bool = True) -> dict[str, int]:
    """Kiểm tra tất cả file trước rồi mới ghi, không để cập nhật dở dang."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    checked: dict[str, tuple[str, bytes, int]] = {}
    for kind, content in uploads.items():
        if kind not in IEEE_FILES:
            raise ValueError(f"Registry không hỗ trợ: {kind}")
        filename, _, size = IEEE_FILES[kind]
        checked[kind] = (filename, content, _validate_ieee_csv(content, kind, size))
    if not checked:
        raise ValueError("Không có file nào để nhập.")
    staged: list[tuple[Path, Path]] = []
    try:
        for kind, (filename, content, _) in checked.items():
            with tempfile.NamedTemporaryFile(mode="wb", dir=root, suffix=".tmp", delete=False) as handle:
                handle.write(content)
                temp_path = Path(handle.name)
            staged.append((temp_path, root / filename))
        for temp_path, target in staged:
            os.replace(temp_path, target)
    finally:
        for temp_path, _ in staged:
            temp_path.unlink(missing_ok=True)
    if update_metadata:
        metadata = {
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "registries": {
                kind: {"rows": count, "sha256": hashlib.sha256(content).hexdigest()}
                for kind, (_, content, count) in checked.items()
            },
            "source": "IEEE Registration Authority public CSV",
        }
        (root / "ieee_metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    return {kind: record[2] for kind, record in checked.items()}


def download_ieee(root: Path, *, timeout: int = 35) -> dict[str, int]:
    """Kết nối chỉ đến 3 URL HTTPS chính thức; không gửi MAC người dùng đi."""
    uploads = {}
    for kind, (_, url, _) in IEEE_FILES.items():
        request = Request(url, headers={"User-Agent": "MAC-OUI-Classifier/1.0 (IEEE public registry reader)", "Accept": "text/csv"})
        with urlopen(request, timeout=timeout) as response:
            payload = response.read(20_000_001)
        uploads[kind] = payload
    return import_ieee_files(root, uploads)


def metadata_date(root: Path) -> str:
    path = Path(root) / "ieee_metadata.json"
    if path.is_file():
        try:
            return str(json.loads(path.read_text(encoding="utf-8")).get("updated_at_utc") or "Không rõ")
        except (ValueError, OSError):
            pass
    return "Chưa có nhật ký cập nhật"
