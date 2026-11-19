# Đưa dự án lên GitHub — không cần biết Git

1. Truy cập https://github.com/new, đăng nhập và tạo kho tên `ai-hr-productivity-hub`.
2. Chọn **Public** nếu muốn dùng làm portfolio. Không chọn tạo README mới vì dự án đã có README.
3. Giải nén ZIP đã tải. Mở thư mục `ai-hr-productivity-hub` bên trong.
4. Tại trang kho mới, chọn **uploading an existing file** (hoặc **Add file → Upload files**).
5. Kéo các tệp và thư mục trong thư mục dự án vào khu vực tải lên; đừng kéo nguyên file ZIP.
6. Đảm bảo có `app.py`, `index.html`, `README.md`, `requirements.txt`, `requirements-dev.txt`, `tests/`, `docs/`, `.github/` và `.gitignore`.
7. Chọn **Commit changes**. Nếu trình duyệt không nhận thư mục ẩn `.github`, dùng GitHub Desktop hoặc tạo thủ công sau.
8. Mở tab **Actions** để kiểm tra bài kiểm thử tự động (có thể cần bật Actions).
9. Vào **Settings → General** và thêm mô tả dự án, hoặc thêm About ở trang chủ kho.
10. Copy URL kho mã nguồn đưa vào CV/portfolio.

**Quan trọng:** GitHub lưu mã nguồn, không chạy FastAPI. GitHub Pages không chạy Python backend; nhấp `index.html` riêng sẽ không đăng nhập được. Muốn thử chức năng phải chạy máy chủ cục bộ như README hướng dẫn.

**Bảo mật:** Không tải lên `.env`, `*.sqlite3`, hồ sơ ứng viên thật, khóa API, mật khẩu thật. File `.env.example` chỉ là mẫu; không tự nạp biến môi trường. Không công khai dịch vụ với tài khoản demo.
