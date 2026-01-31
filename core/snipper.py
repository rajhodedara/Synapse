import sys
import asyncio
import os
import io
from PyQt6.QtWidgets import QApplication, QWidget, QRubberBand
from PyQt6.QtCore import Qt, QPoint, QRect, QThread, pyqtSignal, QBuffer, QIODevice
from PyQt6.QtGui import QPainter, QColor, QGuiApplication

# Image Processing
from PIL import Image, ImageOps

# Windows Native OCR Imports
from winsdk.windows.media.ocr import OcrEngine
from winsdk.windows.graphics.imaging import BitmapDecoder
from winsdk.windows.storage.streams import InMemoryRandomAccessStream, DataWriter

class OCRWorker(QThread):
    finished = pyqtSignal(str, bool)

    def __init__(self, image_data):
        super().__init__()
        self.image_data = image_data

    def run(self):
        try:
            # 1. Preprocessing (Grayscale + Scaling)
            pil_img = Image.open(io.BytesIO(self.image_data))
            pil_img = ImageOps.grayscale(pil_img)
            
            width, height = pil_img.size
            new_size = (width * 2, height * 2)
            pil_img = pil_img.resize(new_size, Image.Resampling.LANCZOS)
            
            byte_arr = io.BytesIO()
            pil_img.save(byte_arr, format='PNG')
            processed_bytes = byte_arr.getvalue()

            # 2. Run Async OCR
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            text = loop.run_until_complete(self.recognize_text(processed_bytes))
            loop.close()
            
            self.finished.emit(text, True)
            
        except Exception as e:
            self.finished.emit(f"Error: {str(e)}", False)

    async def recognize_text(self, data):
        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream)
        writer.write_bytes(data)
        await writer.store_async()
        stream.seek(0)

        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()

        engine = OcrEngine.try_create_from_user_profile_languages()
        if not engine:
            return "Error: No OCR language pack found."

        result = await engine.recognize_async(bitmap)
        
        # --- FIX: Preserve Line Breaks ---
        # Instead of returning result.text, we iterate over result.lines
        lines_text = []
        for line in result.lines:
            lines_text.append(line.text)
            
        # Join lines with a standard newline character
        return "\n".join(lines_text)

class Snipper(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        
        self.virtual_geometry = self.get_virtual_geometry()
        self.setGeometry(self.virtual_geometry)
        
        screen = QGuiApplication.primaryScreen()
        self.screenshot = screen.grabWindow(0)
        
        self.pixel_ratio = self.screenshot.width() / self.virtual_geometry.width()

        self.begin = QPoint()
        self.end = QPoint()
        self.is_snipping = False
        self.rubberband = QRubberBand(QRubberBand.Shape.Rectangle, self)
        
        self.show()

    def get_virtual_geometry(self):
        geometry = QRect()
        for screen in QGuiApplication.screens():
            geometry = geometry.united(screen.geometry())
        return geometry

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.screenshot)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))
        
        if self.is_snipping and not self.rubberband.geometry().isEmpty():
            rect = self.rubberband.geometry()
            src_x = int(rect.x() * self.pixel_ratio)
            src_y = int(rect.y() * self.pixel_ratio)
            src_w = int(rect.width() * self.pixel_ratio)
            src_h = int(rect.height() * self.pixel_ratio)
            source_rect = QRect(src_x, src_y, src_w, src_h)

            painter.drawPixmap(rect, self.screenshot, source_rect)
            painter.setPen(QColor(0, 255, 65))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()

    def mousePressEvent(self, event):
        self.begin = event.pos()
        self.rubberband.setGeometry(QRect(self.begin, self.begin))
        self.rubberband.show()
        self.is_snipping = True

    def mouseMoveEvent(self, event):
        self.end = event.pos()
        self.rubberband.setGeometry(QRect(self.begin, self.end).normalized())
        self.update()

    def mouseReleaseEvent(self, event):
        self.is_snipping = False
        selection_rect = QRect(self.begin, self.end).normalized()
        self.hide()
        
        if selection_rect.width() > 10 and selection_rect.height() > 10:
            self.process_ocr(selection_rect)
        else:
            self.close()

    def process_ocr(self, geometry_rect):
        x = int(geometry_rect.x() * self.pixel_ratio)
        y = int(geometry_rect.y() * self.pixel_ratio)
        w = int(geometry_rect.width() * self.pixel_ratio)
        h = int(geometry_rect.height() * self.pixel_ratio)
        
        img_rect = QRect(x, y, w, h).intersected(self.screenshot.rect())
        cropped = self.screenshot.copy(img_rect)
        
        byte_array = QBuffer()
        byte_array.open(QIODevice.OpenModeFlag.WriteOnly)
        cropped.save(byte_array, "PNG")
        
        self.worker = OCRWorker(byte_array.data())
        self.worker.finished.connect(self.on_ocr_complete)
        self.worker.start()

    def on_ocr_complete(self, text, success):
        if success:
            clean_text = text.strip()
            if clean_text:
                clipboard = QGuiApplication.clipboard()
                clipboard.setText(clean_text)
                print(f"Captured:\n{clean_text}")
            else:
                print("No text detected.")
        else:
            print(f"OCR Error: {text}")
        
        self.close()

if __name__ == "__main__":
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    snipper = Snipper()
    sys.exit(app.exec())