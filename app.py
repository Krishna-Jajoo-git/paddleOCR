from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from paddleocr import PaddleOCR
import io
import os
from PIL import Image
import numpy as np

app = FastAPI(title="PaddleOCR API Server", version="1.0.0")

# Enable CORS for Next.js frontend (e.g. localhost:3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize PaddleOCR engine once at startup
# To enable GPU acceleration on NVIDIA RTX 4050, pass use_gpu=True
USE_GPU = os.getenv("USE_GPU", "False").lower() in ("true", "1", "t")
ocr_engine = PaddleOCR(use_angle_cls=True, lang='en', use_gpu=USE_GPU)

@app.get("/")
def read_root():
    return {
        "status": "online",
        "message": "PaddleOCR backend server is running.",
        "gpu_enabled": USE_GPU
    }

@app.post("/api/ocr")
async def process_image(file: UploadFile = File(...)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File uploaded must be an image.")
    
    try:
        contents = await file.read()
        image = Image.open(io.BytesIO(contents)).convert("RGB")
        img_np = np.array(image)
        
        # Run OCR on uploaded image array
        ocr_result = ocr_engine.ocr(img_np, cls=True)
        
        parsed_results = []
        if ocr_result and len(ocr_result) > 0 and ocr_result[0] is not None:
            for line in ocr_result[0]:
                box = line[0]  # [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
                text, confidence = line[1]
                parsed_results.append({
                    "box": box,
                    "text": text,
                    "confidence": float(confidence)
                })
                
        return {
            "success": True,
            "filename": file.filename,
            "predictions_count": len(parsed_results),
            "results": parsed_results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR processing failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
