# MAC OUI Explorer V3 — Streamlit Cloud Demo

Demo dò Manufacturer không giới hạn danh sách hãng, tra cứu OUI IEEE MA-L (24-bit), MA-M (28-bit), MA-S (36-bit), báo cáo số MAC theo tổ chức đăng ký / Brand và xuất Excel.

## Deploy từ GitHub (không cần server)

1. Tạo repository mới trên GitHub, upload **toàn bộ các file/thư mục** của gói này vào thư mục gốc (gồm `app.py`, `registry.py`, `classifier.py`, `reporting.py`, `requirements.txt`, `category_rules.csv`, `.streamlit/config.toml`).
2. Mở https://share.streamlit.io và đăng nhập bằng tài khoản GitHub, nhấn **Create app**.
3. Chọn đúng repository và branch `main`; **Main file path = `app.py`**. Chọn Python 3.12 nếu được hỏi, bấm Deploy.
4. Trong app, ở sidebar bấm **Tải / cập nhật trực tiếp từ IEEE** để lấy ba file registry. Nếu máy chủ IEEE không truy cập được từ Cloud, tải file qua ba URL ở sidebar rồi upload thủ công.
5. Dùng tab **MAC Lookup**, **Tra cứu hãng IEEE**, hoặc **Import và báo cáo** với `mac_mau.csv`.

## Điểm quan trọng

- Không giới hạn 47 hãng: mọi tên tổ chức có trong IEEE đều có thể tra cứu, không cần thêm rule trước.
- Brand là nhãn chuẩn hóa khi có rule; nếu không có rule sẽ dùng nguyên tên IEEE. Chủng loại chỉ gợi ý theo lĩnh vực, **không xác định** chính xác loại thiết bị/model từ MAC.
- Excel gồm chi tiết, thống kê Brand, thống kê IEEE Manufacturer và nhóm gợi ý.
- Cơ sở IEEE tải về thư mục `data/` trên instance; **Streamlit Cloud có lưu trữ tạm**, redeploy/reboot có thể làm mất dữ liệu tải. Khi đó cập nhật lại.
- App chỉ tải IEEE CSV công khai; không gửi MAC đến API lookup. Nhưng file nhập vẫn được xử lý **trên hạ tầng Streamlit Cloud**. Chỉ sử dụng MAC demo/công khai/lab cá nhân, **không đưa dữ liệu bệnh viện/công ty lên cloud**.
- Một thiết bị có thể có nhiều MAC. Tên tổ chức đăng ký IEEE cũng có thể là nhà sản xuất NIC/OEM chứ không phải nhãn trên thiết bị y tế.

## Chạy cục bộ

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

## Nguồn

- https://standards.ieee.org/products-programs/regauth/
- https://standards-oui.ieee.org/oui/oui.csv
- https://standards-oui.ieee.org/oui28/mam.csv
- https://standards-oui.ieee.org/oui36/oui36.csv
- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy

## V3.1 – Cisco switch MAC address table

Hỗ trợ tự nhận diện dữ liệu từ switch dưới dạng `VLAN,MAC Address,Type,Port`, kể cả Excel/CSV không có hàng tiêu đề. Có thể nhập MAC Cisco `249a.b82c.17c0`, phần mềm tự xác định cột MAC. Báo cáo xuất thêm `Theo VLAN`, `Theo Port`, `VLAN Brand`, `Port Brand`, `VLAN Port`. Cột `STATIC/DYNAMIC` là loại bản ghi, không phải loại thiết bị. Một cổng uplink có thể học nhiều MAC.
