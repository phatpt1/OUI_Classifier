"""Chuẩn hóa vendor / gợi ý chủng loại. KHÔNG suy ra model từ OUI."""
from __future__ import annotations

import csv
from pathlib import Path
import re
from typing import Iterable
from registry import IEEERegistry, address_status, format_mac, normalize_mac

# keyword, nhãn hãng/nhóm, nhóm sản phẩm GỢI Ý. Quy tắc dài hơn luôn có ưu tiên.
DEFAULT_RULES = [
    ("HIKVISION", "Hikvision", "Camera / đầu ghi / giám sát"),
    ("DAHUA", "Dahua", "Camera / đầu ghi / giám sát"),
    ("AXIS COMMUNICATION", "Axis", "Camera / đầu ghi / giám sát"),
    ("UNIVIEW", "Uniview", "Camera / đầu ghi / giám sát"),
    ("HANWHA VISION", "Hanwha Vision", "Camera / đầu ghi / giám sát"),
    ("FORTINET", "Fortinet", "An ninh mạng / firewall"),
    ("PALO ALTO NETWORK", "Palo Alto Networks", "An ninh mạng / firewall"),
    ("SONICWALL", "SonicWall", "An ninh mạng / firewall"),
    ("CHECK POINT", "Check Point", "An ninh mạng / firewall"),
    ("YEALINK", "Yealink", "Điện thoại IP / hội nghị"),
    ("GRANDSTREAM", "Grandstream", "Điện thoại IP / thiết bị mạng"),
    ("POLYCOM", "Poly", "Điện thoại IP / hội nghị"),
    ("SYNOLOGY", "Synology", "NAS / lưu trữ"),
    ("QNAP", "QNAP", "NAS / lưu trữ"),
    ("RUCKUS", "Ruckus", "Mạng không dây / hạ tầng mạng"),
    ("ARUBA", "Aruba", "Mạng không dây / hạ tầng mạng"),
    ("CAMBIUM", "Cambium", "Mạng không dây / hạ tầng mạng"),
    ("UBIQUITI", "Ubiquiti", "Hạ tầng mạng / camera / đa dòng"),
    ("MIKROTIK", "MikroTik", "Hạ tầng mạng / đa dòng"),
    ("JUNIPER", "Juniper", "Hạ tầng mạng / đa dòng"),
    ("CISCO", "Cisco", "Hạ tầng mạng / đa dòng"),
    ("TP-LINK", "TP-Link", "Hạ tầng mạng / đa dòng"),
    ("D-LINK", "D-Link", "Hạ tầng mạng / đa dòng"),
    ("RUIJIE", "Ruijie", "Hạ tầng mạng / đa dòng"),
    ("H3C TECHNOLOG", "H3C", "Hạ tầng mạng / đa dòng"),
    ("HEWLETT PACKARD ENTERPRISE", "HPE", "Server / lưu trữ / hạ tầng mạng"),
    ("HEWLETT-PACKARD", "HP", "Máy tính / máy in / đa dòng"),
    ("HEWLETT PACKARD", "HP", "Máy tính / máy in / đa dòng"),
    ("DELL", "Dell", "Máy tính / server / đa dòng"),
    ("LENOVO", "Lenovo", "Máy tính / thiết bị người dùng"),
    ("APPLE", "Apple", "Máy tính / điện thoại / đa dòng"),
    ("SAMSUNG", "Samsung", "Thiết bị người dùng / điện tử / đa dòng"),
    ("XIAOMI", "Xiaomi", "Thiết bị người dùng / IoT / đa dòng"),
    ("HUAWEI", "Huawei", "Hạ tầng mạng / thiết bị người dùng"),
    ("ZTE", "ZTE", "Hạ tầng mạng / viễn thông"),
    ("EPSON", "Epson", "Máy in / thiết bị hình ảnh"),
    ("BROTHER", "Brother", "Máy in / thiết bị văn phòng"),
    ("CANON", "Canon", "Máy in / camera / thiết bị hình ảnh"),
    ("ZEBRA TECHNOLOG", "Zebra", "Máy in mã vạch / thiết bị công nghiệp"),
    ("HONEYWELL", "Honeywell", "Thiết bị công nghiệp / IoT / đa dòng"),
    ("INTEL", "Intel", "Linh kiện / chip mạng / OEM (không suy ra thiết bị)"),
    ("REALTEK", "Realtek", "Linh kiện / chip mạng / OEM (không suy ra thiết bị)"),
    ("QUALCOMM", "Qualcomm", "Linh kiện / chip mạng / OEM (không suy ra thiết bị)"),
    ("ESPRESSIF", "Espressif", "Linh kiện / chip IoT / OEM (không suy ra thiết bị)"),
    ("HON HAI", "Foxconn / Hon Hai", "Nhà sản xuất OEM (không suy ra thiết bị)"),
    ("FOXCONN", "Foxconn / Hon Hai", "Nhà sản xuất OEM (không suy ra thiết bị)"),
    ("LITE-ON", "Lite-On", "Nhà sản xuất OEM (không suy ra thiết bị)"),
    ("VMWARE", "VMware", "Giao diện mạng ảo (gợi ý)"),
    ("QEMU", "QEMU", "Giao diện mạng ảo (gợi ý)"),
]


def load_rules(path: Path | None = None) -> list[tuple[str, str, str]]:
    rules = []
    if path and Path(path).is_file():
        with Path(path).open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                keyword = (row.get("keyword") or "").strip()
                if keyword and len(keyword) >= 2:
                    rules.append((keyword, (row.get("brand") or "").strip(), (row.get("device_group") or "").strip()))
    return sorted(rules + DEFAULT_RULES, key=lambda x: -len(x[0]))


def infer_group(vendor: str, rules: Iterable[tuple[str, str, str]]) -> tuple[str, str, str]:
    upper = vendor.upper()
    for keyword, brand, group in rules:
        if keyword.upper() in upper:
            return brand or vendor, group or "Chưa xác định", "Suy đoán theo lĩnh vực hãng"
    return vendor, "Chưa xác định", "Không đủ dữ kiện"


def analyze(raw: object, registry: IEEERegistry, rules: list[tuple[str, str, str]]) -> dict[str, str]:
    columns = {
        "MAC chuẩn": "", "Trạng thái MAC": "", "Tổ chức đăng ký IEEE": "", "Brand (tham khảo)": "",
        "Nhóm thiết bị gợi ý": "Chưa xác định", "Loại thiết bị chính xác": "Chưa xác định",
        "Mức tin cậy nhóm": "Không xác định", "Cơ sở phân loại": "", "Loại registry": "", "Tiền tố khớp": "",
    }
    normalized = normalize_mac(raw)
    if normalized is None:
        columns.update({"Trạng thái MAC": "Sai định dạng", "Cơ sở phân loại": "MAC phải đủ 48 bit; hỗ trợ :, -, . hoặc 12 ký tự hex"})
        return columns
    columns["MAC chuẩn"] = format_mac(normalized)
    status = address_status(normalized)
    columns["Trạng thái MAC"] = status
    if status != "MAC toàn cục (unicast)":
        columns["Cơ sở phân loại"] = "Không tra OUI vì địa chỉ đặc biệt hoặc quản trị cục bộ"
        return columns
    match = registry.match(normalized)
    if match is None:
        columns["Cơ sở phân loại"] = "Không tìm thấy trong bản chụp IEEE hiện tại"
        return columns
    columns["Loại registry"] = match.registry
    columns["Tiền tố khớp"] = match.prefix
    columns["Tổ chức đăng ký IEEE"] = " | ".join(match.vendors)
    if len(match.vendors) != 1:
        columns["Cơ sở phân loại"] = "Có nhiều tổ chức cho một tiền tố; cần kiểm tra thủ công"
        return columns
    brand, group, basis = infer_group(match.vendors[0], rules)
    columns["Brand (tham khảo)"] = brand
    columns["Nhóm thiết bị gợi ý"] = group
    columns["Cơ sở phân loại"] = "IEEE: tổ chức đăng ký; " + basis
    columns["Mức tin cậy nhóm"] = "Thấp - suy đoán" if group != "Chưa xác định" else "Không xác định"
    return columns
