# BigData Lead Platform

Công cụ giúp đội kinh doanh bất động sản quản lý và khai thác danh sách khách hàng hiệu quả hơn.

Thông thường, dữ liệu khách hàng nằm rải rác trong rất nhiều file Excel, CSV với định dạng khác nhau, trùng lặp và thiếu thông tin. Dự án này gom tất cả lại một chỗ, làm sạch, bổ sung thông tin còn thiếu, sau đó chấm điểm từng khách hàng để Sales biết nên gọi cho ai trước.

Ngoài ra, hệ thống có thêm phần phân tích quảng cáo Facebook: theo dõi chi phí, đánh giá chất lượng khách hàng mà mỗi chiến dịch mang về và gợi ý nên tăng hay giảm ngân sách.

**Lưu ý:** Repo này chỉ chứa mã nguồn, không kèm bất kỳ dữ liệu khách hàng nào.

## Hệ thống làm được gì

**1. Gom và làm sạch dữ liệu**
Đọc hàng loạt file Excel/CSV, tự xử lý lỗi font tiếng Việt, chuẩn hoá số điện thoại và họ tên, loại bỏ khách hàng bị trùng. Nếu có file đối chiếu, hệ thống sẽ ghép số điện thoại với tài khoản Facebook tương ứng.

**2. Bổ sung thông tin**
Lấy thêm dữ liệu từ các file xuất ra của công cụ quét Facebook và từ kết quả tìm kiếm Google, rồi ghép vào hồ sơ khách hàng đã có.

**3. Chấm điểm khách hàng**
Dùng máy học để chia khách hàng thành từng nhóm có đặc điểm giống nhau, sau đó chấm điểm từ 0 đến 10. Khách từ 8 điểm trở lên được xếp vào nhóm VIP, nên ưu tiên chăm sóc.

**4. Phân tích quảng cáo Facebook**
Kết nối với tài khoản quảng cáo và Fanpage để xem chi phí cho mỗi khách hàng, tỷ lệ nhấp, mức độ lặp lại quảng cáo... Hệ thống đưa ra gợi ý tạm dừng chiến dịch kém hoặc tăng ngân sách cho chiến dịch tốt. Mặc định chế độ này chỉ hiển thị gợi ý, không tự thay đổi quảng cáo thật.

**5. Giao diện xem kết quả**
Có hai trang dashboard chạy trên trình duyệt:
- Trang chính (cổng 5000): danh sách khách hàng, hồ sơ chi tiết, quản lý quảng cáo.
- Trang phân tích (cổng 8502): tình trạng dữ liệu, các nhóm khách hàng, hồ sơ tổng hợp.

## Cài đặt

Cần có Python 3.10 trở lên.

```bash
git clone https://github.com/leozuki/bigdata-platform.git
cd bigdata-platform

python -m venv .venv
.venv\Scripts\activate          # Trên macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt
pip install streamlit
```

Tiếp theo, tạo file cấu hình từ file mẫu:

```bash
copy .env.example .env          # Trên macOS/Linux: cp .env.example .env
```

Mở file `.env` và điền thông tin của bạn. Các mục chính:

- `DATABASE_URL`: nơi lưu dữ liệu. Mặc định dùng SQLite, không cần cài thêm gì.
- `RAW_DATA_DIR`: thư mục chứa các file Excel/CSV gốc.
- `GOOGLE_API_KEY`, `GOOGLE_CSE_ID`: cần nếu muốn tìm thêm thông tin trên Google.
- `META_...`: thông tin ứng dụng, tài khoản quảng cáo và Fanpage Facebook.
- `ADS_DRY_RUN=true`: chỉ xem gợi ý, không thay đổi quảng cáo thật. Nên giữ nguyên cho đến khi đã kiểm tra kỹ.
- `ADS_MOCK_MODE=true`: dùng dữ liệu giả, tiện để chạy thử khi chưa có tài khoản Facebook.

File `.env` chứa mật khẩu và khoá truy cập nên đã được loại khỏi Git. Đừng chia sẻ file này.

## Cách dùng

**Xử lý dữ liệu**

```bash
python main.py                                  # Chạy toàn bộ các bước
python main.py --phase 1 --raw-dir D:/DuLieu    # Chỉ gom và làm sạch dữ liệu
python main.py --phase 2 --fb-csv facebook.csv  # Chỉ bổ sung thông tin
python main.py --phase 3                        # Chỉ chấm điểm khách hàng
```

**Mở giao diện**

```bash
python start.py               # Trang chính: http://localhost:5000
python start.py --streamlit   # Trang phân tích: http://localhost:8502
python start.py --both        # Mở cả hai
```

Trên Windows có thể nhấp đúp vào `start.bat` thay cho lệnh trên.

**Chạy thử với dữ liệu mẫu**

Nếu chưa có dữ liệu thật, có thể tạo dữ liệu giả để thử:

```bash
python tests/generate_sample_data.py
pytest tests/
```

## Cấu trúc thư mục

```
main.py               Chạy các bước xử lý dữ liệu
start.py, start.bat   Mở giao diện dashboard
dashboard/            Trang dashboard chính (Flask)
src/
  phase1_pipeline/    Gom, làm sạch, ghép số điện thoại với Facebook
  phase2_enrichment/  Bổ sung thông tin từ Facebook và Google
  phase3_scoring/     Phân nhóm và chấm điểm khách hàng
  analytics/          Các mô hình phân tích khách hàng
  ads_engine/         Phân tích và tối ưu quảng cáo Facebook
  dashboard/          Trang phân tích (Streamlit)
tests/                Kiểm thử và tạo dữ liệu mẫu
data/                 Để trống, dùng chứa dữ liệu trên máy của bạn
```

## Về dữ liệu cá nhân

Hệ thống này làm việc với thông tin cá nhân như số điện thoại, họ tên, tài khoản mạng xã hội. Khi sử dụng, vui lòng:

- Chỉ xử lý dữ liệu mà bạn có quyền thu thập và sử dụng hợp pháp, tuân thủ Nghị định 13/2023/NĐ-CP về bảo vệ dữ liệu cá nhân.
- Tuân thủ điều khoản sử dụng của Facebook và Google.
- Giữ dữ liệu trong thư mục `data/` trên máy. Thư mục này đã được cấu hình để không bị đưa lên GitHub.

## Công nghệ sử dụng

Python, pandas, scikit-learn, SQLAlchemy, Flask, Streamlit, Facebook Business SDK.
