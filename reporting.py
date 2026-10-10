"""Nhập file và xuất báo cáo; có thể kiểm thử không cần giao diện Streamlit."""
from __future__ import annotations
from io import BytesIO, StringIO
import csv
import re
import pandas as pd
from registry import normalize_mac

def mac_like_header(name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", str(name).lower())
    return normalized in {
        "mac", "macaddress", "physicaladdress", "ethernetaddress", "wirelessmac",
        "bssid", "clientmac", "hardwareaddress", "macaddr", "diachimac",
    } or normalized.endswith("macaddress")


def is_cisco_mac(value) -> bool:
    return bool(normalize_mac(str(value).strip()))


def prepare_mac_table(table: pd.DataFrame) -> pd.DataFrame:
    """Detect headerless Cisco switch MAC tables; preserve every data row."""
    if table.empty:
        return table
    table = table.fillna("").astype(str)
    # Excel/CSV may have consumed the first data row as a column header.
    heads = [str(x).strip() for x in table.columns]
    if len(heads) >= 2 and heads[0].isdigit() and is_cisco_mac(heads[1]):
        table = pd.concat([pd.DataFrame([heads], columns=table.columns), table], ignore_index=True)
        table.columns = [f"Cột {i + 1}" for i in range(len(table.columns))]
    cols = list(table.columns)
    # Headerless Cisco data: VLAN, MAC, TYPE, PORT
    if len(cols) >= 4:
        sample = table.head(40)
        vlan_score = sample.iloc[:, 0].str.fullmatch(r"\d{1,4}").fillna(False).mean()
        mac_score = sample.iloc[:, 1].map(is_cisco_mac).mean()
        type_score = sample.iloc[:, 2].str.upper().isin(["DYNAMIC", "STATIC", "SECURE", "SELF", "SYSTEM"]).mean()
        if vlan_score >= .7 and mac_score >= .7 and type_score >= .5:
            renamed = ["VLAN", "MAC Address", "Type", "Port"] + [str(x) for x in cols[4:]]
            table.columns = renamed
    return table


def identify_network_columns(table: pd.DataFrame) -> tuple[str | None, str | None, str | None]:
    """Return VLAN, type, port column names (if available)."""
    def canonical(x):
        return re.sub(r"[^a-z0-9]", "", str(x).lower())
    fields = {canonical(col): str(col) for col in table.columns}
    return (next((fields[k] for k in ("vlan", "vlanid", "vlannumber") if k in fields), None),
            next((fields[k] for k in ("type", "mactype", "entrytype") if k in fields), None),
            next((fields[k] for k in ("port", "ports", "interface", "interfaces") if k in fields), None))


def mac_column_guess(table: pd.DataFrame) -> str:
    for col in table.columns:
        if mac_like_header(col):
            return str(col)
    sample = table.head(60)
    scores = {col: sample[col].map(is_cisco_mac).mean() for col in table.columns}
    return str(max(scores, key=scores.get)) if scores else str(table.columns[0])


def network_report(data: pd.DataFrame, group_by: list[str], unique_macs: bool = True) -> pd.DataFrame:
    if not group_by or any(col not in data for col in group_by):
        return pd.DataFrame()
    work = data.copy()
    if unique_macs and "MAC chuẩn" in work:
        work = work.loc[work["MAC chuẩn"].fillna("").ne("")].drop_duplicates(subset=group_by + ["MAC chuẩn"])
    grouping = work.groupby(group_by, dropna=False).size().reset_index(name="Số MAC")
    return grouping.sort_values("Số MAC", ascending=False, kind="stable").reset_index(drop=True)


def parse_uploaded(upload) -> pd.DataFrame:
    filename = upload.name.lower()
    payload = upload.getvalue()
    if len(payload) > 25_000_000:
        raise ValueError("File quá lớn (giới hạn 25 MB).")
    if filename.endswith((".xlsx", ".xlsm")):
        table = pd.read_excel(BytesIO(payload), dtype=str, keep_default_na=False, engine="openpyxl")
    elif filename.endswith((".csv", ".tsv")):
        try:
            raw = payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            raw = payload.decode("cp1252")
        try:
            sep = "\t" if filename.endswith(".tsv") else csv.Sniffer().sniff(raw[:8192], delimiters=",;\t").delimiter
        except csv.Error:
            sep = "\t" if filename.endswith(".tsv") else ","
        options = {"sep": sep, "dtype": str, "keep_default_na": False}
        first = raw.splitlines()[0] if raw.splitlines() else ""
        first_column = next(csv.reader([first], delimiter=sep), [""])[0].strip()
        # Một file chỉ có MAC trên mỗi dòng cũng phải giữ được dòng đầu.
        if normalize_mac(first_column) or (first_column.isdigit() and len(next(csv.reader([first], delimiter=sep), [])) >= 2 and is_cisco_mac(next(csv.reader([first], delimiter=sep))[1])):
            options["header"] = None
        table = pd.read_csv(StringIO(raw), **options)
        if "header" in options and options["header"] is None:
            table.columns = ["MAC"] + [f"Cột {idx + 2}" for idx in range(len(table.columns) - 1)]
    elif filename.endswith(".txt"):
        lines = [ln.strip() for ln in payload.decode("utf-8-sig").splitlines() if ln.strip()]
        if lines and mac_like_header(lines[0]):
            lines = lines[1:]
        table = pd.DataFrame({"MAC": lines})
    else:
        raise ValueError("Hỗ trợ CSV, TSV, TXT, XLSX, XLSM.")
    if table.empty:
        raise ValueError("File không có dữ liệu.")
    if len(table) > 200_000:
        raise ValueError("Vui lòng chia file thành các phần tối đa 200.000 dòng.")
    table.columns = [str(x).strip() for x in table.columns]
    return prepare_mac_table(table)


def csv_bytes(data: pd.DataFrame) -> bytes:
    # Tránh CSV formula injection nếu được mở bằng Excel.
    output = data.copy()
    for column in output.columns:
        output[column] = output[column].map(
            lambda x: ("'" + x) if isinstance(x, str) and x.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else x
        )
    return output.to_csv(index=False).encode("utf-8-sig")


def group_table(data: pd.DataFrame, column: str, name: str) -> pd.DataFrame:
    counts = data[column].fillna("").replace("", "Chưa xác định").value_counts(dropna=False)
    return counts.rename_axis(name).reset_index(name="Số lượng")


def brand_report(data: pd.DataFrame, unique_macs: bool = True) -> pd.DataFrame:
    """Aggregate IEEE-associated brands; unknowns are explicit, not hidden.

    Each unique valid MAC is one address, not necessarily one physical device.
    """
    working = data.copy()
    if unique_macs and "MAC chuẩn" in working:
        good = working["MAC chuẩn"].fillna("").ne("")
        working = pd.concat([
            working.loc[good].drop_duplicates(subset=["MAC chuẩn"]),
            working.loc[~good],
        ], ignore_index=True)
    if "Brand (tham khảo)" not in working:
        raise ValueError("Thiếu cột Brand (tham khảo)")
    brands = working["Brand (tham khảo)"].fillna("").str.strip().replace("", "Chưa xác định")
    counts = brands.value_counts().rename_axis("Brand").reset_index(name="Số MAC")
    counts["Tỷ lệ (%)"] = (counts["Số MAC"] / len(working) * 100).round(2) if len(working) else 0.0
    return counts


def manufacturer_report(data: pd.DataFrame) -> pd.DataFrame:
    """Unique normalized MAC addresses grouped by exact IEEE registered organization."""
    if "Tổ chức đăng ký IEEE" not in data.columns:
        return pd.DataFrame(columns=["IEEE Manufacturer", "Số lượng"])
    working = data
    if "MAC chuẩn" in working.columns:
        working = working.loc[working["MAC chuẩn"].fillna("").ne("")].drop_duplicates(subset=["MAC chuẩn"])
    return group_table(working, "Tổ chức đăng ký IEEE", "IEEE Manufacturer")


def excel_bytes(data: pd.DataFrame) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(
        bio, engine="xlsxwriter", engine_kwargs={"options": {"strings_to_formulas": False, "strings_to_urls": False}}
    ) as writer:
        datasets = {
            "Chi tiet": data,
            "Theo hang": brand_report(data, unique_macs=False).rename(columns={"Số MAC": "Số lượng"}),
            "IEEE manufacturers": manufacturer_report(data),
            "Theo hang unique": brand_report(data, unique_macs=True),
            "Theo nhom": group_table(data, "Nhóm thiết bị gợi ý", "Nhóm gợi ý"),
            "Theo trang thai": group_table(data, "Trạng thái MAC", "Trạng thái"),
            "Huong dan": pd.DataFrame({
                "Thông tin": ["Manufacturer", "Brand", "Nhóm thiết bị", "Loại chính xác", "Dữ liệu đầu vào", "Nguồn IEEE", "Giới hạn"],
                "Giải thích": [
                    "Đơn vị được đăng ký MAC theo bản dữ liệu IEEE đã tải, không nhất thiết là nhãn trên sản phẩm.",
                    "Nhãn chuẩn hóa từ tên tổ chức đăng ký, mang tính tham khảo.",
                    "Chỉ là giả định theo lĩnh vực kinh doanh của hãng, KHÔNG xác định đúng model/chức năng.",
                    "Luôn để Chưa xác định nếu không có dữ liệu bổ sung (hostname, SNMP, LLDP, inventory...).",
                    "Ứng dụng xử lý cục bộ; không upload danh sách MAC tới máy chủ tra cứu bên ngoài.",
                    "https://standards.ieee.org/products-programs/regauth/",
                    "MAC cục bộ (U/L=1), multicast, sai định dạng không được nhận diện hãng từ OUI.",
                ],
            }),
        }
        vlan_col, type_col, port_col = identify_network_columns(data)
        if vlan_col:
            datasets["Theo VLAN"] = network_report(data, [vlan_col])
            datasets["VLAN Brand"] = network_report(data, [vlan_col, "Brand (tham khảo)"])
        if port_col:
            datasets["Theo Port"] = network_report(data, [port_col])
            datasets["Port Brand"] = network_report(data, [port_col, "Brand (tham khảo)"])
        if vlan_col and port_col:
            datasets["VLAN Port"] = network_report(data, [vlan_col, port_col])
        for sheet_name, sheet_data in datasets.items():
            sheet_data.to_excel(writer, sheet_name=sheet_name, index=False)
            sheet = writer.sheets[sheet_name]
            header_fmt = writer.book.add_format({"bold": True, "fg_color": "#15324F", "font_color": "#FFFFFF", "valign": "vcenter", "text_wrap": True})
            sheet.set_row(0, 30, header_fmt)
            sheet.freeze_panes(1, 0)
            sheet.autofilter(0, 0, len(sheet_data), max(len(sheet_data.columns) - 1, 0))
            for idx, name in enumerate(sheet_data.columns):
                width = min(52, max(16, len(str(name)) + 3))
                if name == "Cơ sở phân loại":
                    width = 52
                sheet.set_column(idx, idx, width)
    return bio.getvalue()


