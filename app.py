"""MAC Vendor & Device Classifier - offline-first Streamlit dashboard."""
from __future__ import annotations

from io import BytesIO, StringIO
from pathlib import Path
import csv
import re

import pandas as pd
import streamlit as st

from classifier import analyze, load_rules
from registry import IEEE_FILES, IEEERegistry, download_ieee, import_ieee_files, metadata_date
from reporting import parse_uploaded, mac_like_header, group_table, brand_report, manufacturer_report, csv_bytes, excel_bytes, mac_column_guess, identify_network_columns, network_report, prepare_mac_table

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
RULE_PATH = ROOT / "category_rules.csv"

st.set_page_config(page_title="MAC OUI Classifier", page_icon="🛜", layout="wide")

st.markdown("""
<style>
.block-container { padding-top: 1.6rem; }
div[data-testid="stMetric"] { padding: 12px 16px; border: 1px solid rgba(127,127,127,.20); border-radius: 12px; }
.subtle {color: #6b7280;}
</style>
""", unsafe_allow_html=True)


@st.cache_resource(show_spinner=False)
def get_registry(version_key: tuple) -> IEEERegistry:
    return IEEERegistry(DATA_DIR)


st.title("MAC OUI Explorer — IEEE Manufacturer Discovery")
st.caption("Demo Streamlit Cloud • Toàn bộ hãng IEEE • MAC Lookup • Thống kê theo tổ chức • Không cần danh sách hãng cố định")
st.warning("DEMO PUBLIC CLOUD: Chỉ sử dụng MAC giả lập / dữ liệu công khai / lab riêng. Không upload dữ liệu inventory hoặc MAC từ hệ thống bệnh viện.", icon="🔒")

with st.sidebar:
    st.header("Cơ sở dữ liệu IEEE")
    version_key = tuple((name, (DATA_DIR / details[0]).stat().st_mtime_ns if (DATA_DIR / details[0]).exists() else 0) for name, details in IEEE_FILES.items())
    registry = get_registry(version_key)
    st.metric("Số tiền tố IEEE đã nạp", f"{registry.total:,}")
    ieee_orgs = {vendor for bucket in registry.prefixes.values() for vendors in bucket.values() for vendor in vendors}
    st.metric("Tổ chức đăng ký khác nhau", f"{len(ieee_orgs):,}")
    for key in IEEE_FILES:
        st.caption(f"{key}: {registry.counts.get(key, 0):,} tiền tố")
    st.caption("Cập nhật: " + metadata_date(DATA_DIR))
    if st.button("↻ Tải / cập nhật trực tiếp từ IEEE", use_container_width=True, type="primary"):
        with st.spinner("Đang tải ba registry chính thức qua HTTPS..."):
            try:
                counts = download_ieee(DATA_DIR)
                get_registry.clear()
                st.success("Đã cập nhật: " + ", ".join(f"{k}: {v:,}" for k, v in counts.items()))
                st.rerun()
            except Exception as exc:
                st.error(f"Không thể cập nhật tự động: {exc}")
                st.info("Tải thủ công các file IEEE ở mục bên dưới, rồi nhập lại. Không dùng nguồn không rõ xuất xứ.")
    with st.expander("Nhập ba file IEEE thủ công"):
        st.markdown("Trong mạng bị chặn Internet, hãy tải ba file CSV từ trang IEEE trên một máy khác:")
        for kind, (filename, url, _) in IEEE_FILES.items():
            st.markdown(f"[{kind} — {filename}]({url})")
        registry_uploads = {}
        for kind in IEEE_FILES:
            file_upload = st.file_uploader(f"File {kind}", type=["csv"], key=f"registry_{kind}")
            if file_upload:
                registry_uploads[kind] = file_upload.getvalue()
        if st.button("Nạp các file IEEE đã chọn", disabled=not registry_uploads):
            try:
                counts = import_ieee_files(DATA_DIR, registry_uploads)
                get_registry.clear()
                st.success("Đã nhập: " + ", ".join(f"{k}: {v:,}" for k, v in counts.items()))
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    with st.expander("Tuỳ chỉnh phân loại"):
        st.markdown("Danh mục 47 Brand chỉ là **quy tắc nhãn tùy chọn**, KHÔNG giới hạn tra cứu. Tên tổ chức chưa có rule vẫn hiển thị và được thống kê. Có thể sửa `category_rules.csv` trong GitHub để thêm quy tắc.")
        st.code("keyword,brand,device_group\nExampleVendor,DemoBrand,Nhóm demo", language="csv")
        st.caption("Quy tắc tự thêm có ưu tiên khi từ khóa dài hơn; chỉ dùng gợi ý, không xác minh model.")

tab_inventory, tab_lookup, tab_ieee = st.tabs(["📊 Import và báo cáo", "🔎 MAC Lookup", "🏭 Tra cứu hãng IEEE"])

with tab_ieee:
    st.subheader("Khám phá toàn bộ tổ chức đăng ký IEEE")
    st.caption("Tìm tên tổ chức trong bản dữ liệu đã tải. Không cần nằm trong 47 quy tắc Brand.")
    query_org = st.text_input("Tìm tên tổ chức", placeholder="Ví dụ: medical, philips, mindray, siemens, roche...")
    if registry.total == 0:
        st.info("Bấm tải dữ liệu IEEE ở thanh bên để bắt đầu.")
    elif query_org.strip():
        q = query_org.strip().casefold()
        found = []
        for size, kind in ((6, "MA-L"), (7, "MA-M"), (9, "MA-S")):
            for prefix, vendors in registry.prefixes[size].items():
                for org in vendors:
                    if q in org.casefold():
                        found.append({"IEEE Organization": org, "Prefix": prefix, "Registry": kind})
                        if len(found) >= 2000:
                            break
                if len(found) >= 2000: break
            if len(found) >= 2000: break
        st.metric("Kết quả đang hiển thị", len(found))
        st.dataframe(pd.DataFrame(found), use_container_width=True, hide_index=True)
        st.caption("Tối đa 2.000 dòng mỗi lượt tìm kiếm. Tên IEEE là đơn vị sở hữu dải MAC, không nhất thiết là hãng trên thiết bị.")

with tab_lookup:
    st.subheader("Tra cứu MAC riêng lẻ (IEEE Lookup)")
    lookup_value = st.text_input("Nhập địa chỉ MAC", placeholder="00:11:22:33:44:55 hoặc 0011.2233.4455", key="single_lookup")
    if lookup_value.strip():
        lookup = analyze(lookup_value, registry, load_rules(RULE_PATH))
        if lookup["Trạng thái MAC"] == "Sai định dạng":
            st.error("MAC không đúng định dạng 48 bit.")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Brand (tham khảo)", lookup["Brand (tham khảo)"] or "Chưa xác định")
            c2.metric("Registry", lookup["Loại registry"] or "Không khớp")
            c3.metric("Trạng thái", lookup["Trạng thái MAC"])
            st.dataframe(pd.DataFrame([lookup]).T.rename(columns={0:"Kết quả"}), use_container_width=True)
            st.caption("MAC Lookup sử dụng dữ liệu IEEE đã nạp trên máy chủ Streamlit, không gửi MAC tới dịch vụ lookup bên ngoài.")
    else:
        st.info("Nhập một MAC để xem tổ chức đăng ký IEEE, brand, tiền tố khớp và chủng loại gợi ý.")

with tab_inventory:
    st.subheader("1. Nhập danh sách MAC")
    method = st.radio("Nguồn nhập", ["Tải file", "Dán danh sách"], horizontal=True, label_visibility="collapsed")
    try:
        if method == "Tải file":
            source = st.file_uploader("Chọn CSV / TSV / TXT / Excel", type=["csv", "tsv", "txt", "xlsx", "xlsm"])
            table = parse_uploaded(source) if source else None
        else:
            pasted = st.text_area("Mỗi MAC trên một dòng; có thể kèm dòng tiêu đề MAC", height=140, placeholder="00:11:22:33:44:55\n00-1A-2B-CC-DD-EE\n0011.2233.4455")
            lines = [x.strip() for x in pasted.splitlines() if x.strip()]
            if lines and mac_like_header(lines[0]):
                lines = lines[1:]
            if lines and any(len(re.split(r"\s+", ln)) >= 4 for ln in lines):
                parts = [re.split(r"\s+", ln) for ln in lines]
                table = prepare_mac_table(pd.DataFrame(parts).fillna(""))
            else:
                table = pd.DataFrame({"MAC": lines}) if lines else None
    except Exception as exc:
        st.error(f"Không đọc được file: {exc}")
        table = None

    if table is None:
        st.info("Chọn file hoặc dán danh sách MAC để bắt đầu. Nếu chưa có registry, tải dữ liệu IEEE ở thanh bên trái.")
        st.stop()

    guessed_column = mac_column_guess(table)
    selected_index = list(table.columns).index(guessed_column)
    selected_column = st.selectbox("Cột chứa MAC Address", list(table.columns), index=selected_index)
    st.caption(f"Đã nhận {len(table):,} dòng. App bảo toàn các cột gốc và các MAC bị trùng.")

    if registry.total == 0:
        st.warning("Chưa có dữ liệu IEEE. Vẫn có thể chuẩn hoá/kiểm tra MAC, nhưng chưa nhận diện được hãng. Hãy tải registry ở thanh bên trái.")

    rules = load_rules(RULE_PATH)
    with st.spinner("Đang xử lý MAC..."):
        rows = [analyze(value, registry, rules) for value in table[selected_column].tolist()]
        result = pd.concat([table.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
        raw_name = "MAC gốc" if "MAC gốc" not in result.columns else "MAC gốc (copy)"
        row_name = "Dòng đầu vào" if "Dòng đầu vào" not in result.columns else "Dòng đầu vào (copy)"
        result.insert(len(table.columns), raw_name, table[selected_column].tolist())
        result.insert(len(table.columns) + 1, row_name, list(range(1, len(result) + 1)))

    st.subheader("2. Kết quả phân loại")
    recognized = result["Tổ chức đăng ký IEEE"].ne("").sum()
    locally = result["Trạng thái MAC"].str.startswith("MAC cục bộ").sum()
    invalid = result["Trạng thái MAC"].ne("MAC toàn cục (unicast)").sum() - locally
    with st.container():
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Tổng MAC", f"{len(result):,}")
        col2.metric("Khớp IEEE", f"{recognized:,}")
        col3.metric("MAC cục bộ", f"{locally:,}")
        col4.metric("Không hợp lệ / nhóm", f"{invalid:,}")

    filter_a, filter_b, filter_c = st.columns([1, 1, 2])
    with filter_a:
        statuses = ["Tất cả"] + sorted(result["Trạng thái MAC"].unique().tolist())
        status_selected = st.selectbox("Trạng thái", statuses)
    with filter_b:
        groups = ["Tất cả"] + sorted(result["Nhóm thiết bị gợi ý"].unique().tolist())
        group_selected = st.selectbox("Nhóm gợi ý", groups)
    with filter_c:
        keyword = st.text_input("Tìm MAC / tên tổ chức / brand", placeholder="Ví dụ: Cisco, Hikvision, 00:11...")

    filtered = result
    if status_selected != "Tất cả":
        filtered = filtered.loc[filtered["Trạng thái MAC"] == status_selected]
    if group_selected != "Tất cả":
        filtered = filtered.loc[filtered["Nhóm thiết bị gợi ý"] == group_selected]
    if keyword.strip():
        relevant = ["MAC chuẩn", "Tổ chức đăng ký IEEE", "Brand (tham khảo)", "Nhóm thiết bị gợi ý"]
        mask = filtered[relevant].apply(lambda col: col.str.contains(keyword.strip(), case=False, regex=False)).any(axis=1)
        filtered = filtered.loc[mask]
    st.dataframe(filtered, use_container_width=True, hide_index=True, height=min(580, max(230, len(filtered) * 34 + 38)))
    st.caption(f"Hiển thị {len(filtered):,}/{len(result):,} dòng. Các gợi ý chủng loại KHÔNG phải kết quả nhận dạng thiết bị chính xác.")

    vlan_col, type_col, port_col = identify_network_columns(result)
    if vlan_col or port_col:
        st.subheader("3. Thống kê Switch MAC Address Table")
        st.caption("Đếm số địa chỉ MAC học được, không khẳng định số thiết bị vật lý. Cổng uplink có thể học nhiều MAC từ switch khác.")
        vtab, ptab, mixtab = st.tabs(["Theo VLAN", "Theo Port", "VLAN × Brand"])
        with vtab:
            if vlan_col:
                st.dataframe(network_report(result, [vlan_col]), use_container_width=True, hide_index=True)
            else:
                st.info("Không nhận thấy cột VLAN.")
        with ptab:
            if port_col:
                st.dataframe(network_report(result, [port_col]), use_container_width=True, hide_index=True)
                if vlan_col:
                    st.dataframe(network_report(result, [vlan_col, port_col]), use_container_width=True, hide_index=True)
            else:
                st.info("Không nhận thấy cột Port.")
        with mixtab:
            if vlan_col:
                st.dataframe(network_report(result, [vlan_col, "Brand (tham khảo)"]), use_container_width=True, hide_index=True)
            else:
                st.info("Không nhận thấy cột VLAN.")
    st.subheader("4. Báo cáo theo tổ chức IEEE và Brand")
    ieee_summary = manufacturer_report(result)
    st.markdown("**Tất cả nhà sản xuất/tổ chức IEEE xuất hiện trong dữ liệu**")
    st.dataframe(ieee_summary, use_container_width=True, hide_index=True)
    st.download_button("⬇ Xuất thống kê Manufacturer (CSV)", csv_bytes(ieee_summary), file_name="ieee_manufacturers.csv", mime="text/csv")
    st.markdown("**Thống kê Brand (tên chuẩn hóa khi có quy tắc)**")
    unique_mode = st.toggle("Đếm MAC duy nhất (loại bỏ MAC trùng)", value=True, help="Đây là số địa chỉ MAC; một thiết bị có thể có nhiều MAC.")
    summary = brand_report(result, unique_macs=unique_mode)
    reported_total = int(summary["Số MAC"].sum())
    known_total = int(summary.loc[summary["Brand"] != "Chưa xác định", "Số MAC"].sum())
    b1, b2, b3 = st.columns(3)
    b1.metric("Số MAC trong báo cáo", f"{reported_total:,}")
    b2.metric("Số Brand đã nhận diện", f"{(summary['Brand'] != 'Chưa xác định').sum():,}")
    b3.metric("MAC có Brand", f"{known_total:,}")
    st.dataframe(summary, use_container_width=True, hide_index=True)
    st.download_button("⬇ Xuất thống kê Brand (CSV)", csv_bytes(summary), file_name="bao_cao_so_luong_brand.csv", mime="text/csv", use_container_width=True)
    st.caption("Không giới hạn hãng: hãng ngoài quy tắc vẫn dùng nguyên tên IEEE. Đơn vị: địa chỉ MAC (hoặc dòng nhập), không phải số thiết bị vật lý.")

    chart_l, chart_r = st.columns(2)
    with chart_l:
        st.markdown("**Thống kê theo Brand (10 nhóm lớn nhất)**")
        brand_counts = summary.rename(columns={"Số MAC": "Số lượng"})[["Brand", "Số lượng"]].head(10)
        st.bar_chart(brand_counts.set_index("Brand"), horizontal=True)
    with chart_r:
        st.markdown("**Thống kê nhóm thiết bị gợi ý**")
        group_counts = group_table(result, "Nhóm thiết bị gợi ý", "Nhóm gợi ý").head(10)
        st.bar_chart(group_counts.set_index("Nhóm gợi ý"), horizontal=True)

    st.subheader("5. Xuất báo cáo")
    left, right = st.columns(2)
    with left:
        st.download_button(
            "⬇ Xuất CSV (danh sách đang lọc)", data=csv_bytes(filtered),
            file_name="mac_oui_result.csv", mime="text/csv", use_container_width=True,
        )
    with right:
        st.download_button(
            "⬇ Xuất Excel (toàn bộ + thống kê)", data=excel_bytes(result),
            file_name="mac_oui_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True,
        )

    with st.expander("Giới hạn kỹ thuật & bảo mật"):
        st.markdown("""
    - **IEEE không xác định chính xác loại thiết bị**: cùng một nhà đăng ký có thể làm nhiều loại sản phẩm; NIC có thể do hãng OEM sản xuất.
    - Địa chỉ **locally administered** (`U/L=1`) hoặc **multicast** không nên gán hãng theo tiền tố OUI; có thể là MAC Wi-Fi ngẫu nhiên hoặc giao diện ảo.
    - Một số MAC có thể bị đổi, giả mạo hoặc copy. Việc khớp IEEE không xác minh danh tính thực tế của thiết bị.
    - Không quét mạng và không gửi MAC người dùng ra dịch vụ bên ngoài. Nút cập nhật chỉ tải các tệp công khai từ IEEE.
    - Để nhận diện đến **camera / access point / switch / model** với độ tin cậy cao hơn cần bổ sung tín hiệu như DHCP fingerprint, LLDP/CDP, SNMP, mDNS, hostname, dữ liệu inventory được phép sử dụng.
    - Chỉ dùng dữ liệu công khai, dữ liệu giả lập hoặc dữ liệu trong lab cá nhân của bạn; không đưa dữ liệu của bên thứ ba vào ứng dụng nếu không được phép.
    """)
