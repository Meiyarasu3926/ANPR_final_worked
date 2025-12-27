# ocr_worker.py - ENHANCED VERSION
import cv2
import re
import numpy as np
from paddleocr import PaddleOCR

ocr = PaddleOCR(lang="en", use_angle_cls=True, show_log=False)

PLATE_REGEX = r"^[A-Z]{2}\d{2}[A-Z]{1,2}\d{3,4}$"

INDIAN_STATE_CODES = {
    "AN","AP","AR","AS","BR","CG","CH","DD","DL","DN","GA","GJ","HP","HR",
    "JH","JK","KA","KL","LA","LD","MH","ML","MN","MP","MZ","NL","OD","PB",
    "PY","RJ","SK","TN","TR","TS","UK","UP","WB"
}

def clean_plate(text):
    """Clean and validate plate number"""
    text = re.sub(r"[^A-Z0-9]", "", text.upper())
    
    if not re.match(PLATE_REGEX, text):
        return None
    
    # Validate Indian state code
    if text[:2] not in INDIAN_STATE_CODES:
        return None
    
    return text


def preprocess_method_1_grayscale_binary(crop):
    """Method 1: Simple grayscale + adaptive threshold"""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 11, 2
    )
    return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)


def preprocess_method_2_clahe(crop):
    """Method 2: CLAHE enhancement"""
    # Convert to LAB color space
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    
    # Apply CLAHE to L channel
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    
    # Merge and convert back
    enhanced = cv2.merge([l, a, b])
    enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
    
    # Apply sharpening
    kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
    sharpened = cv2.filter2D(enhanced, -1, kernel)
    
    return sharpened


def preprocess_method_3_morphology(crop):
    """Method 3: Morphological operations"""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    
    # Apply bilateral filter to reduce noise while keeping edges
    denoised = cv2.bilateralFilter(gray, 9, 75, 75)
    
    # Morphological gradient
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    gradient = cv2.morphologyEx(denoised, cv2.MORPH_GRADIENT, kernel)
    
    # Threshold
    _, binary = cv2.threshold(gradient, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # Close gaps
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 1))
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    
    return cv2.cvtColor(closed, cv2.COLOR_GRAY2BGR)


def preprocess_method_4_contrast_stretch(crop):
    """Method 4: Contrast stretching + unsharp mask"""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    
    # Contrast stretching
    p2, p98 = np.percentile(gray, (2, 98))
    stretched = np.clip((gray - p2) * (255 / (p98 - p2)), 0, 255).astype(np.uint8)
    
    # Unsharp mask
    gaussian = cv2.GaussianBlur(stretched, (0, 0), 2.0)
    unsharp = cv2.addWeighted(stretched, 1.5, gaussian, -0.5, 0)
    
    # Adaptive threshold
    binary = cv2.adaptiveThreshold(
        unsharp, 255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY, 15, 10
    )
    
    return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)


def preprocess_method_5_edge_enhance(crop):
    """Method 5: Edge enhancement + bilateral filter"""
    # Bilateral filter to preserve edges
    bilateral = cv2.bilateralFilter(crop, 9, 75, 75)
    
    gray = cv2.cvtColor(bilateral, cv2.COLOR_BGR2GRAY)
    
    # Sobel edge detection
    sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    sobel = np.sqrt(sobelx**2 + sobely**2)
    sobel = np.uint8(sobel / sobel.max() * 255)
    
    # Combine with original
    combined = cv2.addWeighted(gray, 0.7, sobel, 0.3, 0)
    
    # Otsu threshold
    _, binary = cv2.threshold(combined, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)


def preprocess_method_6_histogram_equalization(crop):
    """Method 6: Histogram equalization"""
    # Convert to YUV
    yuv = cv2.cvtColor(crop, cv2.COLOR_BGR2YUV)
    
    # Equalize Y channel
    yuv[:, :, 0] = cv2.equalizeHist(yuv[:, :, 0])
    
    # Convert back
    equalized = cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR)
    
    # Sharpen
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    sharpened = cv2.filter2D(equalized, -1, kernel)
    
    return sharpened


def multi_preprocess_ocr(crop):
    """
    Try multiple preprocessing methods and return best result.
    Returns: (plate_number, confidence)
    """
    # Resize if too small
    h, w = crop.shape[:2]
    if max(h, w) < 180:
        scale = 180 / max(h, w)
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    
    # All preprocessing methods
    preprocessing_methods = [
        ("Original", crop),
        ("Grayscale+Binary", preprocess_method_1_grayscale_binary(crop)),
        ("CLAHE+Sharpen", preprocess_method_2_clahe(crop)),
        ("Morphology", preprocess_method_3_morphology(crop)),
        ("Contrast+Unsharp", preprocess_method_4_contrast_stretch(crop)),
        ("Edge+Bilateral", preprocess_method_5_edge_enhance(crop)),
        ("Histogram+Sharpen", preprocess_method_6_histogram_equalization(crop)),
    ]
    
    best_plate = None
    best_conf = 0.0
    best_method = None
    
    for method_name, processed_img in preprocessing_methods:
        try:
            # Run OCR
            results = ocr.ocr(processed_img, cls=True) or []
            
            # Extract text
            for line in results:
                if not line:
                    continue
                for item in line:
                    if len(item) < 2:
                        continue
                    
                    text, conf = item[1]
                    
                    # Clean and validate
                    plate = clean_plate(text)
                    
                    if plate and conf > best_conf:
                        best_plate = plate
                        best_conf = conf
                        best_method = method_name
                        
                        # Early exit if high confidence
                        if conf > 0.92:
                            print(f"âœ… High confidence plate: {plate} ({conf:.2f}) via {method_name}")
                            return best_plate, best_conf
        
        except Exception as e:
            print(f"âš ï¸ Error in {method_name}: {e}")
            continue
    
    if best_plate:
        print(f"ðŸ“‹ Best plate: {best_plate} ({best_conf:.2f}) via {best_method}")
    else:
        print(f"âŒ No valid plate found in any preprocessing method")
    
    return best_plate, best_conf


# ============================================================
# TESTING FUNCTION
# ============================================================
def test_ocr_on_image(image_path):
    """Test function to see all preprocessing results"""
    img = cv2.imread(image_path)
    if img is None:
        print(f"âŒ Could not load image: {image_path}")
        return
    
    print(f"\nðŸ” Testing OCR on: {image_path}")
    print("="*60)
    
    plate, conf = multi_preprocess_ocr(img)
    
    print("="*60)
    if plate:
        print(f"âœ… FINAL RESULT: {plate} (Confidence: {conf:.4f})")
    else:
        print(f"âŒ FINAL RESULT: No valid plate detected")
    print()


if __name__ == "__main__":
    # Test with sample images
    import sys
    
    if len(sys.argv) > 1:
        test_ocr_on_image(sys.argv[1])
    else:
        print("Usage: python ocr_worker.py <image_path>")