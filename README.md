# PaddleOCR Backend Setup

This directory contains the Python environment and FastAPI server for **PaddleOCR**.

## Setup Overview
- **Python Version**: Python 3.11.17 (Downloaded & configured in `C:\Users\Krishna\paddleOCR_venv`)
- **GPU Device Detected**: NVIDIA GeForce RTX 4050 Laptop GPU (CUDA Drivers 581.86 / CUDA 13.0 / 12.x supported)
- **PaddleOCR Version**: 2.9.1 (Stable release)
- **Framework**: FastAPI with CORS enabled for Next.js TypeScript frontend integration

## How to Start the FastAPI Server

Run the PowerShell start script or execute the command below:

```powershell
& "C:\Users\Krishna\paddleOCR_venv\Scripts\python.exe" app.py
```

The server will start at `http://localhost:8000`.

### API Endpoints
- `GET http://localhost:8000/` - Health check & GPU status
- `POST http://localhost:8000/api/ocr` - Upload image (multipart/form-data) and receive bounding boxes, text & confidence scores.

## Next.js TypeScript Frontend Integration Example

```typescript
const formData = new FormData();
formData.append("file", imageFile);

const response = await fetch("http://localhost:8000/api/ocr", {
  method: "POST",
  body: formData,
});

const data = await response.json();
console.log(data.results);
```
