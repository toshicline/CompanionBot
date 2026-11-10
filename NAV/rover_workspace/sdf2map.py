#!/usr/bin/env python3
"""
SDF2MAP - SDF/World to Map Converter with 2D Mesh Projection
"""
import sys
import os
import math
import yaml
import numpy as np
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                           QWidget, QPushButton, QLabel, QLineEdit, QFileDialog,
                           QTextEdit, QGroupBox, QGridLayout, QSpinBox,
                           QDoubleSpinBox, QProgressBar, QMessageBox, 
                           QScrollArea, QDialog, 
                           QGraphicsView, QGraphicsScene)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QRectF
from PyQt5.QtGui import QFont, QPixmap, QPainter, QImage

from PIL import Image, ImageDraw

try:
    from scipy import ndimage
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

from sdf_parser import SDFParser

# =============== Zoomable Map View ===============

class ZoomableMapView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.pixmap_item = None

        self.zoom_factor = 1.0
        self.min_zoom, self.max_zoom = 0.05, 20.0

        self.last_pan_point = None
        self.is_panning = False

        self.setDragMode(QGraphicsView.NoDrag)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setMinimumSize(600, 400)
        self.setStyleSheet("border: 2px solid #e2e8f0; border-radius: 8px; background-color: #ccc;")

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setResizeAnchor(QGraphicsView.NoAnchor)

        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setOptimizationFlags(QGraphicsView.DontAdjustForAntialiasing)
        

    def set_image(self, pil_image):
        if pil_image is None:
            self.scene.clear()
            self.pixmap_item = None
            return

        max_size = 4096
        original_size = pil_image.size

        if max(original_size) > max_size:
            ratio = min(max_size / original_size[0], max_size / original_size[1])
            new_size = (int(original_size[0] * ratio), int(original_size[1] * ratio))
            display_image = pil_image.resize(new_size, Image.LANCZOS)
        else:
            display_image = pil_image

        display_image = display_image.convert("RGBA")
        data = display_image.tobytes("raw", "RGBA")
        w, h = display_image.size
        qimage = QImage(data, w, h, QImage.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimage)

        self.scene.clear()
        self.pixmap_item = self.scene.addPixmap(pixmap)

        margin = max(pixmap.width(), pixmap.height()) * 0.2  
        rect = QRectF(pixmap.rect()).adjusted(-margin, -margin, margin, margin)
        self.scene.setSceneRect(rect)

        self.resetTransform()
        self.zoom_factor = 1.0
        self.fitInView(self.pixmap_item, Qt.KeepAspectRatio)
        
        map_convert = SDFToMapConverter()
        map_convert.log_message(f"Map loaded: {original_size} -> {display_image.size}")

    def wheelEvent(self, event):
        if not self.pixmap_item:
            return
        zoom_in_factor = 1.15
        if event.angleDelta().y() > 0:
            factor = zoom_in_factor
        else:
            factor = 1.0 / zoom_in_factor

        new_zoom = self.zoom_factor * factor
        if not (self.min_zoom <= new_zoom <= self.max_zoom):
            return

        old_scene_pos = self.mapToScene(event.pos())

        self.scale(factor, factor)
        self.zoom_factor = new_zoom

        new_scene_pos = self.mapToScene(event.pos())
        diff = new_scene_pos - old_scene_pos
        center = self.mapToScene(self.viewport().rect().center())
        self.centerOn(center - diff)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.pixmap_item is not None:
            self.is_panning = True
            self.last_pan_point = self.mapToScene(event.pos())
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_panning and self.last_pan_point is not None:
            current_scene_pos = self.mapToScene(event.pos())
            delta = current_scene_pos - self.last_pan_point
            center = self.mapToScene(self.viewport().rect().center())
            self.centerOn(center - delta)
            self.last_pan_point = current_scene_pos
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_panning:
            self.is_panning = False
            self.last_pan_point = None
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def reset_view(self):
        if self.pixmap_item:
            self.resetTransform()
            self.fitInView(self.pixmap_item, Qt.KeepAspectRatio)
            self.zoom_factor = 1.0

    def fit_to_window(self):
        if self.pixmap_item:
            self.fitInView(self.scene.itemsBoundingRect(), Qt.KeepAspectRatio)
            transform = self.transform()
            self.zoom_factor = transform.m11()

# =============== 2D PROJECTION MAP GENERATION ===============

def compute_world_bounds(shapes, margin=1.0):
    """Compute world bounds from shapes"""
    if not shapes:
        return -5.0, -5.0, 5.0, 5.0
        
    bounds = []
    for s in shapes:
        x, y, z = s['position']
        if s['type'] in ['box', 'mesh', 'plane', 'polyline']:
            sx, sy = s['size'][0], s['size'][1]
            bounds.extend([(x-sx/2, y-sy/2), (x+sx/2, y+sy/2)])
        elif s['type'] in ['cylinder', 'sphere']:
            r = s['size'][0]
            bounds.extend([(x-r, y-r), (x+r, y+r)])
    
    xs, ys = zip(*bounds)
    return min(xs)-margin, min(ys)-margin, max(xs)+margin, max(ys)+margin

def draw_mesh_projection(draw, shape, world_to_px, model_resolver):
    """
    Draw mesh using 2D projection with INTERNAL STRUCTURE
    Renders all triangles, not just the outer hull
    """
    if not model_resolver:
        return False
    
    mesh_uri = shape.get('resolved_uri') or shape.get('uri')
    if not mesh_uri:
        return False
    
    transform = shape['transform']
    mesh_scale = shape.get('mesh_scale', (1.0, 1.0, 1.0))
    
    # Get 2D projection
    projected_2d = model_resolver.get_mesh_2d_projection(mesh_uri, transform, mesh_scale)
    
    map_convert = SDFToMapConverter()
    
    if projected_2d is None or len(projected_2d) < 3:
        map_convert.log_message(f"Could not project mesh: {os.path.basename(mesh_uri)}")
    
        return False
    
    # Convert to pixel coordinates
    pixel_points = []
    for point_2d in projected_2d:
        px, py = world_to_px(point_2d[0], point_2d[1])
        pixel_points.append((px, py))
    
    # Draw ALL triangles (internal structure included) - NO OUTLINES
    if len(pixel_points) >= 3:
        triangles_drawn = 0
        
        # STL files store vertices in groups of 3 (triangles)
        for i in range(0, len(pixel_points) - 2, 3):
            triangle = pixel_points[i:i+3]
            if len(triangle) == 3:
                # Draw filled triangle WITHOUT outline (None instead of 0)
                draw.polygon(triangle, fill=0, outline=None)
                triangles_drawn += 1
        
        map_convert.log_message(f"Drew {triangles_drawn} solid triangles for {os.path.basename(mesh_uri)}")
        return True
    
    return False

def draw_single_shape(draw, shape, world_to_px, scale_factor, resolution, model_resolver=None):
    """
    Draw shape with 2D projection support for meshes
    """
    shape_type = shape['type']
    x, y, z = shape['position']
    roll, pitch, yaw = shape['rotation']
    size = shape['size']
    
    if shape_type == 'box':
        sx, sy, sz = size
        half_x, half_y = sx/2, sy/2
        cos_yaw, sin_yaw = math.cos(yaw), math.sin(yaw)
        
        corners = [(-half_x, -half_y), (half_x, -half_y), (half_x, half_y), (-half_x, half_y)]
        pixel_corners = []
        
        for cx, cy in corners:
            rx = cx * cos_yaw - cy * sin_yaw + x
            ry = cx * sin_yaw + cy * cos_yaw + y
            pixel_corners.append(world_to_px(rx, ry))
        
        if len(pixel_corners) >= 3:
            draw.polygon(pixel_corners, fill=0, outline=0)
            
    elif shape_type == 'polyline':
        if 'points' not in shape:
            return

        x_offset, y_offset, _ = shape['position']
        points = shape['points']
        height = shape.get('height', 1.0)

        cos_yaw, sin_yaw = math.cos(yaw), math.sin(yaw)
        transformed_points = []

        for px, py in points:
            rx = px * cos_yaw - py * sin_yaw + x_offset
            ry = px * sin_yaw + py * cos_yaw + y_offset
            transformed_points.append(world_to_px(rx, ry))

        if len(transformed_points) >= 2:
            thickness = max(1, int(height * scale_factor / resolution / 20))
            draw.line(transformed_points, fill=0, width=thickness)

    elif shape_type == 'cylinder':
        radius, length = size[0], size[1] if len(size) > 1 else 1.0
        tilt_factor = abs(math.sin(pitch)) + abs(math.sin(roll))
        
        if tilt_factor > 0.1:
            semi_major = max(radius, (length / 2) * tilt_factor)
            semi_minor = radius * (1 - tilt_factor * 0.3)
            points = []
            for angle in range(0, 360, 10):
                rad = math.radians(angle)
                ex = semi_major * math.cos(rad)
                ey = semi_minor * math.sin(rad)
                rotated_ex = ex * math.cos(yaw) - ey * math.sin(yaw) + x
                rotated_ey = ex * math.sin(yaw) + ey * math.cos(yaw) + y
                points.append(world_to_px(rotated_ex, rotated_ey))
            if len(points) > 2:
                draw.polygon(points, fill=0, outline=0)
        else:
            px, py = world_to_px(x, y)
            rp = max(2, int(math.ceil(radius * scale_factor / resolution)))
            draw.ellipse([px-rp, py-rp, px+rp, py+rp], fill=0, outline=0)
            
    elif shape_type == 'sphere':
        radius = size[0]
        px, py = world_to_px(x, y)
        rp = max(2, int(math.ceil(radius * scale_factor / resolution)))
        draw.ellipse([px-rp, py-rp, px+rp, py+rp], fill=0, outline=0)
        
    elif shape_type == 'mesh':
        # Try 2D projection first
        if shape.get('use_projection') and model_resolver:
            success = draw_mesh_projection(draw, shape, world_to_px, model_resolver)
            if success:
                return  # Successfully drew projection
        
    elif shape_type == 'plane':
        sx, sy, sz = size
        half_x, half_y = sx/2, sy/2
        cos_yaw, sin_yaw = math.cos(yaw), math.sin(yaw)
        
        corners = [(-half_x, -half_y), (half_x, -half_y), (half_x, half_y), (-half_x, half_y)]
        pixel_corners = []
        
        for cx, cy in corners:
            rx = cx * cos_yaw - cy * sin_yaw + x
            ry = cx * sin_yaw + cy * cos_yaw + y
            pixel_corners.append(world_to_px(rx, ry))
        
        if len(pixel_corners) >= 3:
            draw.polygon(pixel_corners, fill=0, outline=0)

def shapes_to_occupancy_with_projection(shapes, resolution=0.05, margin=1.0, min_wall_thickness=0.1, 
                                       lidar_height=None, map_size_scale=1.0, super_sampling=4,
                                       model_resolver=None):
    """
    Generate occupancy map with 2D mesh projection support
    """
    # Filter by LIDAR height
    if lidar_height is not None:
        lidar_height_m = lidar_height / 100.0
        filtered_shapes = []
        for shape in shapes:
            z_center = shape['position'][2]
            
            if shape['type'] in ['box', 'mesh', 'plane', 'polyline']:
                z_size = shape['size'][2] if len(shape['size']) > 2 else 1.0
                z_min, z_max = z_center - z_size/2, z_center + z_size/2
            elif shape['type'] == 'cylinder':
                z_size = shape['size'][1] if len(shape['size']) > 1 else 1.0
                z_min, z_max = z_center - z_size/2, z_center + z_size/2
            elif shape['type'] == 'sphere':
                radius = shape['size'][0]
                z_min, z_max = z_center - radius, z_center + radius
            else:
                z_min, z_max = z_center - 0.5, z_center + 0.5
            
            if z_min <= lidar_height_m <= z_max:
                filtered_shapes.append(shape)
        shapes = filtered_shapes
    
    # Calculate dimensions
    minx, miny, maxx, maxy = compute_world_bounds(shapes, margin)
    width_m, height_m = maxx - minx, maxy - miny
    
    effective_resolution = resolution / map_size_scale
    w = max(100, int(math.ceil(width_m / effective_resolution)))
    h = max(100, int(math.ceil(height_m / effective_resolution)))
    
    scale_factor = super_sampling
    high_res_w, high_res_h = w * scale_factor, h * scale_factor
    
    map_convert = SDFToMapConverter()
    map_convert.log_message(f"Generating map: {w}x{h} pixels (High-res: {high_res_w}x{high_res_h})")
    map_convert.log_message(f"World: {width_m:.2f}x{height_m:.2f}m, Resolution: {effective_resolution:.4f}m/px")
    
    # Create high-res image
    high_res_img = Image.new('L', (high_res_w, high_res_h), color=255)
    high_res_draw = ImageDraw.Draw(high_res_img)
    
    def world_to_px_high_res(world_x, world_y):
        px = int((world_x - minx) * scale_factor / effective_resolution)
        py = high_res_h - 1 - int((world_y - miny) * scale_factor / effective_resolution)
        return max(0, min(high_res_w-1, px)), max(0, min(high_res_h-1, py))
    
    # Sort by area
    sorted_shapes = sorted(shapes, key=lambda s: s['size'][0] * s['size'][1] if len(s['size']) >= 2 else 1.0, reverse=True)
    
    # Apply minimum thickness
    for shape in sorted_shapes:
        shape_type = shape['type']
        
        if shape_type in ['box', 'mesh', 'plane']:
            sx, sy, sz = shape['size']
            
            if sx < min_wall_thickness or sy < min_wall_thickness:
                shape = shape.copy()
                new_sx = max(sx, min_wall_thickness)
                new_sy = max(sy, min_wall_thickness)
                shape['size'] = (new_sx, new_sy, sz)
                
                if shape_type == 'mesh' and (sx < 0.5 or sy < 0.5):
                    shape['size'] = (
                        max(new_sx, min_wall_thickness * 3),
                        max(new_sy, min_wall_thickness * 3),
                        sz
                    )
        
        # Draw shape (with projection support)
        draw_single_shape(high_res_draw, shape, world_to_px_high_res, scale_factor, effective_resolution, model_resolver)
    
    # Resize to final
    final_img = high_res_img.resize((w, h), Image.LANCZOS)
    
    # Enhance contrast
    img_array = np.array(final_img)
    enhanced = np.where(img_array > 200, 255, img_array)
    enhanced = np.where(enhanced < 100, 0, enhanced)
    
    mask = (enhanced >= 100) & (enhanced <= 200)
    enhanced[mask] = np.where(enhanced[mask] < 150, 0, 255)
    
    # Morphological operations
    if map_size_scale > 1.0 and SCIPY_AVAILABLE:
        try:
            enhanced = ndimage.binary_opening(enhanced < 128, structure=np.ones((2,2)))
            enhanced = np.where(enhanced, 0, 255).astype(np.uint8)
        except:
            pass
    
    return Image.fromarray(enhanced.astype(np.uint8)), (minx, miny, 0.0)

# =============== Missing Models Dialog ===============

class MissingModelsDialog(QDialog):
    def __init__(self, missing_models, parent=None):
        super().__init__(parent)
        self.missing_models = list(set(missing_models))
        self.user_paths = {}
        self.skip_missing = False
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("Missing Models")
        self.setModal(True)
        self.resize(700, 400)
        
        layout = QVBoxLayout(self)
        info_label = QLabel("Select your model path ")
        layout.addWidget(info_label)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        form_layout = QVBoxLayout(container)
        
        for model in self.missing_models:
            block = QWidget()
            block_layout = QVBoxLayout(block)
            
            model_label = QLabel(model)
            model_label.setStyleSheet("font-weight: bold; color: #333;")
            block_layout.addWidget(model_label)
            
            path_row = QHBoxLayout()
            path_edit = QLineEdit()
            path_edit.setPlaceholderText("Select file...")
            path_row.addWidget(path_edit)
            
            browse_btn = QPushButton("Browse")
            browse_btn.clicked.connect(lambda checked, m=model, edit=path_edit: self.browse_model_path(m, edit))
            path_row.addWidget(browse_btn)
            
            block_layout.addLayout(path_row)
            form_layout.addWidget(block)
            self.user_paths[model] = path_edit
        
        scroll.setWidget(container)
        layout.addWidget(scroll)
        
        button_layout = QHBoxLayout()
        skip_btn = QPushButton("Skip Missing")
        skip_btn.clicked.connect(self.skip_models)
        skip_btn.setStyleSheet("QPushButton { background-color: #ff4d4d; border: 1px solid #ff4d4d; color: white; font-weight: bold;  }")
        button_layout.addWidget(skip_btn)
        
        button_layout.addStretch()
        
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        ok_btn.setStyleSheet("QPushButton { background-color: #10b981; border: 1px solid #10b981; color: white; font-weight: bold }")
        button_layout.addWidget(ok_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
    
    def browse_model_path(self, model_name, path_edit):
        file_path, _ = QFileDialog.getOpenFileName(
            self, f"Select file for {model_name}", "",
            "All Supported (*.sdf *.stl *.STL *.dae *.obj);;SDF (*.sdf);;STL (*.stl) (*.STL) ;;DAE (*.dae);;OBJ (*.obj)"
        )
        
        if file_path:
            path_edit.setText(file_path)
    
    def skip_models(self):
        self.skip_missing = True
        self.accept()
    
    def get_user_paths(self):
        paths = {}
        for model, path_edit in self.user_paths.items():
            path = path_edit.text().strip()
            if path and os.path.isfile(path):
                paths[model] = path
                if not model.startswith('model://'):
                    paths[f'model://{model}'] = path
        return paths

# =============== Conversion Thread ===============

class MapConversionThread(QThread):
    progress_update = pyqtSignal(int)
    status_update = pyqtSignal(str)
    conversion_complete = pyqtSignal(bool, str, object, object)
    models_missing = pyqtSignal(list)
    
    def __init__(self, input_file, output_dir, conversion_params, user_model_paths=None, skip_missing=False, preview_only=False):
        super().__init__()
        self.input_file = input_file
        self.output_dir = output_dir
        self.conversion_params = conversion_params
        self.user_model_paths = user_model_paths or {}
        self.skip_missing = skip_missing
        self.preview_only = preview_only
        self._stop_requested = False
        
    def stop(self):
        self._stop_requested = True
        
    def run(self):
        try:
            if self._stop_requested:
                return
                
            self.status_update.emit("Starting conversion with 2D mesh projection...")
            self.progress_update.emit(10)
            
            sdf_parser = SDFParser()
            self.progress_update.emit(20)
            
            if self._stop_requested:
                return
            
            def status_callback(message):
                if not self._stop_requested:
                    self.status_update.emit(message)
            
            self.status_update.emit("Parsing SDF file...")
            parsed_data = sdf_parser.parse_file(
                self.input_file, 
                self.user_model_paths, 
                self.skip_missing, 
                status_callback
            )
            
            if self._stop_requested:
                return
            
            missing_models = sdf_parser.get_missing_models()
            if missing_models and not self.skip_missing:
                unresolved = []
                if isinstance(self.user_model_paths, dict):
                    for missing in missing_models:
                        possible_keys = [missing, f"model://{missing}"]
                        if not any(key in self.user_model_paths for key in possible_keys):
                            unresolved.append(missing)
                else:
                    unresolved = missing_models
                    
                if unresolved:
                    self.models_missing.emit(unresolved)
                    return
            
            self.progress_update.emit(50)
            shapes = sdf_parser.get_shapes()
            
            if self._stop_requested:
                return
            
            if not shapes:
                raise Exception("No shapes found")
                
            stats = sdf_parser.get_statistics()
            self.status_update.emit(f"Found {stats['total_shapes']} shapes")
            self.progress_update.emit(70)
            
            if self._stop_requested:
                return
            
            self.status_update.emit("Generating map with 2D mesh projection...")
            img, origin = shapes_to_occupancy_with_projection(
                shapes, 
                resolution=self.conversion_params.get('resolution', 0.05),
                margin=self.conversion_params.get('margin', 1.0),
                min_wall_thickness=self.conversion_params.get('min_wall_thickness', 0.1),
                lidar_height=self.conversion_params.get('lidar_height', None),
                map_size_scale=self.conversion_params.get('map_size_scale', 1.0),
                super_sampling=self.conversion_params.get('super_sampling', 4),
                model_resolver=sdf_parser.model_resolver
            )
            
            if self._stop_requested:
                return
            
            self.progress_update.emit(90)
            
            if not self.preview_only:
                self.status_update.emit("Saving files...")
                base_name = os.path.splitext(os.path.basename(self.input_file))[0]
                pgm_file = os.path.join(self.output_dir, f"{base_name}.pgm")
                yaml_file = os.path.join(self.output_dir, f"{base_name}.yaml")
                
                # Save PGM
                img_array = np.array(img)
                with open(pgm_file, 'wb') as f:
                    f.write(b'P5\n')
                    f.write(f'{img_array.shape[1]} {img_array.shape[0]}\n'.encode())
                    f.write(b'255\n')
                    f.write(img_array.tobytes())
                
                # Save YAML with specific order
                from collections import OrderedDict
                yaml_content = OrderedDict([
                    ('image', os.path.basename(pgm_file)),
                    ('mode', 'trinary'),
                    ('resolution', float(self.conversion_params.get('resolution', 0.05))),
                    ('origin', [float(origin[0]), float(origin[1]), float(origin[2])]),
                    ('negate', 0),
                    ('occupied_thresh', float(self.conversion_params.get('occupied_thresh', 0.65))),
                    ('free_thresh', float(self.conversion_params.get('free_thresh', 0.25)))
                ])
                
                with open(yaml_file, 'w') as f:
                    yaml.dump(yaml_content, f, default_flow_style=False, sort_keys=False)
                
                success_message = f"Files saved:\n{pgm_file}\n{yaml_file}"
            else:
                success_message = f"Preview generated: {img.size[0]}x{img.size[1]} pixels"
            
            if self._stop_requested:
                return
                
            self.progress_update.emit(100)
            self.status_update.emit("Conversion complete!")
            self.conversion_complete.emit(True, success_message, img, origin)
            
        except Exception as e:
            if not self._stop_requested:
                self.status_update.emit(f"Failed: {str(e)}")
                self.conversion_complete.emit(False, f"Error: {str(e)}", None, None)

# =============== Main Application ===============

class SDFToMapConverter(QMainWindow):
    def __init__(self):
        super().__init__()
        self.conversion_thread = None
        self.generated_map = None
        self.generated_origin = None
        self.generated_conversion_params = None
        self.user_model_paths = {}
        self.skip_missing_models = False
        self.init_ui()
        
    def closeEvent(self, event):
        if self.conversion_thread and self.conversion_thread.isRunning():
            self.log_message("Stopping conversion...")
            self.conversion_thread.terminate()
            self.conversion_thread.wait(3000)
            if self.conversion_thread.isRunning():
                self.conversion_thread.kill()
        event.accept()
        
    def init_ui(self):
        self.setWindowTitle("SDF2MAP")
        self.setGeometry(50, 0, 1400, 800)
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        
        # Title
        title = QLabel("SDF2MAP Converter")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.setStyleSheet("color: #2E3440; padding: 10px; background-color: #ECEFF4; border-radius: 5px;")
        layout.addWidget(title)
        
        # Main content
        content_layout = QVBoxLayout()
        
        # Top panel
        up_panel = QHBoxLayout()
        vbox = QVBoxLayout()
        self.create_input_section(vbox)
        self.create_controls_section(vbox)
        up_panel.addLayout(vbox)
        self.create_parameters_section(up_panel)
        
        # Bottom panel
        down_panel = QHBoxLayout()
        self.create_preview_section(down_panel)
        self.create_status_section(down_panel)
        down_panel.setStretch(0, 2)  
        down_panel.setStretch(1, 1)  
        
        content_layout.addLayout(up_panel)
        content_layout.addLayout(down_panel)
        layout.addLayout(content_layout)
    
    def create_input_section(self, parent_layout):
        group = QGroupBox("Input Configuration")
        layout = QGridLayout(group)
        
        layout.addWidget(QLabel("Input File:"), 0, 0)
        self.input_file_edit = QLineEdit()
        self.input_file_edit.setPlaceholderText("Select SDF or World file...")
        layout.addWidget(self.input_file_edit, 0, 1)
        
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_input_file)
        layout.addWidget(browse_btn, 0, 2)
        
        layout.addWidget(QLabel("Output Dir:"), 1, 0)
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setText(os.getcwd())
        layout.addWidget(self.output_dir_edit, 1, 1)
        
        output_browse_btn = QPushButton("Browse")
        output_browse_btn.clicked.connect(self.browse_output_dir)
        layout.addWidget(output_browse_btn, 1, 2)
        
        info_label = QLabel(" ")
        info_label.setStyleSheet("color: gray; font-style: italic; font-size: 10px;")
        layout.addWidget(info_label, 2, 0, 1, 3)
        
        parent_layout.addWidget(group)
    
    def create_parameters_section(self, parent_layout):
        group = QGroupBox("Map Parameters")
        layout = QGridLayout(group)  
        
        layout.addWidget(QLabel("Resolution:"), 0, 0)
        self.resolution_spin = QDoubleSpinBox()
        self.resolution_spin.setRange(0.001, 1.0)
        self.resolution_spin.setValue(0.05)
        self.resolution_spin.setSuffix(" m/px")
        layout.addWidget(self.resolution_spin, 0, 1)
        
        layout.addWidget(QLabel("Map Size Scale:"), 0, 2)
        self.map_size_spin = QDoubleSpinBox()
        self.map_size_spin.setRange(0.5, 5.0)
        self.map_size_spin.setValue(1.0)
        self.map_size_spin.setSingleStep(0.1)
        self.map_size_spin.setDecimals(1)
        self.map_size_spin.setSuffix("x")
        layout.addWidget(self.map_size_spin, 0, 3)
        
        layout.addWidget(QLabel("Super Sampling:"), 1, 0)
        self.super_sampling_spin = QSpinBox()
        self.super_sampling_spin.setRange(1, 8)
        self.super_sampling_spin.setValue(4)
        self.super_sampling_spin.setSuffix("x")
        layout.addWidget(self.super_sampling_spin, 1, 1)
        
        layout.addWidget(QLabel("LIDAR Height:"), 1, 2)
        self.lidar_height_spin = QSpinBox()
        self.lidar_height_spin.setRange(-100, 500)
        self.lidar_height_spin.setValue(20)
        self.lidar_height_spin.setSuffix(" cm")
        layout.addWidget(self.lidar_height_spin, 1, 3)
        
        layout.addWidget(QLabel("Min Wall Thickness:"), 2, 0)
        self.min_wall_spin = QDoubleSpinBox()
        self.min_wall_spin.setRange(0.01, 2.0)
        self.min_wall_spin.setValue(0.1)
        self.min_wall_spin.setSingleStep(0.01)
        self.min_wall_spin.setDecimals(3)
        self.min_wall_spin.setSuffix(" m")
        layout.addWidget(self.min_wall_spin, 2, 1)
        
        layout.addWidget(QLabel("World Margin:"), 2, 2)
        self.margin_spin = QDoubleSpinBox()
        self.margin_spin.setRange(0.0, 50.0)
        self.margin_spin.setValue(1.0)
        self.margin_spin.setSuffix(" m")
        layout.addWidget(self.margin_spin, 2, 3)
        
        preset_layout = QHBoxLayout()
        preset_data = [("Fast", 0.1, 1.0, 2), ("Standard", 0.05, 1.0, 4), ("High Quality", 0.02, 1.5, 6)]
        for name, res, size, sampling in preset_data:
            btn = QPushButton(name)
            btn.clicked.connect(lambda checked, r=res, s=size, sa=sampling: self.apply_preset(r, s, sa))
            preset_layout.addWidget(btn)
        layout.addLayout(preset_layout, 3, 0, 1, 4) 
        
        parent_layout.addWidget(group)
        
    def apply_preset(self, resolution, size_scale, super_sampling):
        self.resolution_spin.setValue(resolution)
        self.map_size_spin.setValue(size_scale)
        self.super_sampling_spin.setValue(super_sampling)
        self.log_message(f"Preset applied: {resolution}m/px, {size_scale}x, {super_sampling}x sampling")
    
    def create_controls_section(self, parent_layout):
        layout = QVBoxLayout()
        
        self.convert_btn = QPushButton("Convert to Map (Preview)")
        self.convert_btn.clicked.connect(self.start_conversion_preview)
        self.convert_btn.setStyleSheet("QPushButton { background-color: #10b981; border: 1px solid #10b981; color: white; font-weight: bold; padding: 12px; border-radius: 6px; }")
        layout.addWidget(self.convert_btn)
        
        self.save_btn = QPushButton("Save Map Files")
        self.save_btn.clicked.connect(self.save_map_files)
        self.save_btn.setEnabled(False)
        self.save_btn.setStyleSheet("QPushButton { background-color: #1d3748; color: white; font-weight: bold; padding: 12px; border-radius: 6px; } QPushButton:disabled { background-color: #1d3748; }")
        layout.addWidget(self.save_btn)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        parent_layout.addLayout(layout)
    
    def create_preview_section(self, parent_layout):
        group = QGroupBox("Map Preview")
        layout = QVBoxLayout(group)
        
        zoom_layout = QHBoxLayout()
        
        self.zoom_in_btn = QPushButton("Zoom In")
        self.zoom_in_btn.clicked.connect(lambda: self.map_view.scale(1.2, 1.2) and self.update_zoom_display())
        zoom_layout.addWidget(self.zoom_in_btn)
        
        self.zoom_out_btn = QPushButton("Zoom Out")
        self.zoom_out_btn.clicked.connect(lambda: self.map_view.scale(0.8, 0.8) and self.update_zoom_display())
        zoom_layout.addWidget(self.zoom_out_btn)
        
        self.fit_window_btn = QPushButton("Fit Window")
        self.fit_window_btn.clicked.connect(lambda: self.map_view.fit_to_window() and self.update_zoom_display())
        zoom_layout.addWidget(self.fit_window_btn)
        
        zoom_layout.addStretch()
        
        self.zoom_info_label = QLabel("Zoom: 100%")
        self.zoom_info_label.setStyleSheet("color: #1d3748; font-weight: bold;")
        zoom_layout.addWidget(self.zoom_info_label)

        layout.addLayout(zoom_layout)
        
        self.map_view = ZoomableMapView()
        layout.addWidget(self.map_view)
        
        parent_layout.addWidget(group)
    
    def create_status_section(self, parent_layout):
        group = QGroupBox("Status Log")
        layout = QVBoxLayout(group)
        
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setFont(QFont("Consolas", 9))
        self.status_text.setStyleSheet("background-color: #1d3748; color: #e2e8f0;")
        
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.status_text.clear)

        layout.addWidget(clear_btn)
        layout.addWidget(self.status_text)

        parent_layout.addWidget(group)
        
        self.log_message("SDF2MAP ready")
        self.log_message("Supports: STL, OBJ, DAE mesh files")
    
    def browse_input_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select SDF/World File", "", 
            "All Supported (*.sdf *.world);;SDF Files (*.sdf);;World Files (*.world)"
        )
        if file_path:
            self.input_file_edit.setText(file_path)
            self.log_message(f"Input: {os.path.basename(file_path)}")
    
    def browse_output_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if dir_path:
            self.output_dir_edit.setText(dir_path)
    
    def log_message(self, message):
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.status_text.append(f"<span style='color: #68d391;'>[{timestamp}]</span> {message}")
        QApplication.processEvents()
    
    def update_zoom_display(self):
        if hasattr(self, 'zoom_info_label') and hasattr(self, 'map_view'):
            zoom_percentage = int(self.map_view.zoom_factor * 100)
            self.zoom_info_label.setText(f"Zoom: {zoom_percentage}%")
    
    def handle_missing_models(self, missing_models):
        dialog = MissingModelsDialog(missing_models, self)
        if dialog.exec_() == QDialog.Accepted:
            if dialog.skip_missing:
                self.skip_missing_models = True
                self.log_message(f"Skipping {len(missing_models)} missing models")
            else:
                new_paths = dialog.get_user_paths()
                if not isinstance(self.user_model_paths, dict):
                    self.user_model_paths = {}
                self.user_model_paths.update(new_paths)
                for uri, path in new_paths.items():
                    self.log_message(f"Mapped {uri} -> {os.path.basename(path)}")
            self.start_conversion_internal(preview_only=True)
        else:
            self.convert_btn.setEnabled(True)
            self.progress_bar.setVisible(False)
    
    def start_conversion_preview(self):
        self.skip_missing_models = False
        self.start_conversion_internal(preview_only=True)
    
    def start_conversion_internal(self, preview_only=True):
        input_file = self.input_file_edit.text().strip()
        output_dir = self.output_dir_edit.text().strip()
        self.log_message(f"Starting conversion process...")
        self.log_message(f"Input file: {input_file}")
        self.log_message(f"Output directory: {output_dir}")
        
        if not input_file or not os.path.exists(input_file):
            QMessageBox.warning(self, "Invalid Input", "Select a valid input file")
            return
        
        if not preview_only and (not output_dir or not os.path.exists(output_dir)):
            QMessageBox.warning(self, "Invalid Output", "Select a valid output directory")
            return
        
        conversion_params = {
            'resolution': self.resolution_spin.value(),
            'lidar_height': self.lidar_height_spin.value(),
            'margin': self.margin_spin.value(),
            'min_wall_thickness': self.min_wall_spin.value(),
            'map_size_scale': self.map_size_spin.value(),
            'super_sampling': self.super_sampling_spin.value(),
            'occupied_thresh': 0.65,
            'free_thresh': 0.25,
        }
        
        expected_res = conversion_params['resolution'] / conversion_params['map_size_scale']
        self.log_message(f"Effective resolution: {expected_res:.4f} m/px")
        
        self.generated_conversion_params = conversion_params.copy()
        
        self.convert_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        self.conversion_thread = MapConversionThread(
            input_file, output_dir, conversion_params, 
            self.user_model_paths, self.skip_missing_models, preview_only
        )
        
        self.conversion_thread.progress_update.connect(self.progress_bar.setValue)
        self.conversion_thread.status_update.connect(self.log_message)
        self.conversion_thread.conversion_complete.connect(self.on_conversion_complete)
        self.conversion_thread.models_missing.connect(self.handle_missing_models)
        self.conversion_thread.start()
    
    def on_conversion_complete(self, success, message, image, origin):
        self.convert_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        if success:
            self.generated_map = image
            self.generated_origin = origin
            
            if image:
                self.map_view.set_image(image)
                self.save_btn.setEnabled(True)
                self.update_zoom_display()
            
            self.log_message("Conversion complete with 2D projection!")
        else:
            self.log_message(f"Failed: {message}")
            QMessageBox.critical(self, "Conversion Failed", message)
    
    def save_map_files(self):
        if not self.generated_map or not self.generated_conversion_params:
            QMessageBox.warning(self, "No Map", "Generate preview first")
            return
        
        try:
            input_file = self.input_file_edit.text()
            output_dir = self.output_dir_edit.text()
            
            if not output_dir or not os.path.exists(output_dir):
                QMessageBox.warning(self, "Invalid Output", "Select valid output directory")
                return
            
            base_name = os.path.splitext(os.path.basename(input_file))[0]
            pgm_file = os.path.join(output_dir, f"{base_name}.pgm")
            yaml_file = os.path.join(output_dir, f"{base_name}.yaml")
            
            # Save PGM
            img_array = np.array(self.generated_map)
            with open(pgm_file, 'wb') as f:
                f.write(b'P5\n')
                f.write(f'{img_array.shape[1]} {img_array.shape[0]}\n'.encode())
                f.write(b'255\n')
                f.write(img_array.tobytes())
            
            # Round numbers to 5 decimal places for cleaner output
            def round_num(x):
                return round(float(x), 5)
            
            yaml_content = {
                'image': os.path.basename(pgm_file),
                'mode': 'trinary',
                'resolution': round_num(self.generated_conversion_params['resolution']),
                'origin': [
                    round_num(self.generated_origin[0]),
                    round_num(self.generated_origin[1]),
                    round_num(self.generated_origin[2])
                ],
                'negate': 0,
                'occupied_thresh': round_num(self.generated_conversion_params['occupied_thresh']),
                'free_thresh': round_num(self.generated_conversion_params['free_thresh'])
            }

            # ✅ custom representer to print short lists inline
            def represent_list(dumper, data):
                if len(data) <= 3:
                    return dumper.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=True)
                return dumper.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=False)

            yaml.add_representer(list, represent_list)

            with open(yaml_file, 'w') as f:
                yaml.dump(yaml_content, f, default_flow_style=False, sort_keys=False)
            
            self.log_message("Files saved successfully!")
            QMessageBox.information(self, "Saved", f"Files saved:\n{pgm_file}\n{yaml_file}")
            
        except Exception as e:
            self.log_message(f"Save error: {str(e)}")
            QMessageBox.critical(self, "Error", f"Save error: {str(e)}")

if __name__ == "__main__":
    import signal
    
    def signal_handler(signum, frame):
        QApplication.instance().quit()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        app = QApplication(sys.argv)
        app.setApplicationName("SDF2MAP")
        
        app.setStyleSheet("""
            QMainWindow { background-color: #f7fafc; }
            QGroupBox {
                font-weight: bold; border: 2px solid #e2e8f0; border-radius: 8px;
                margin-top: 1ex; padding-top: 12px; background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 10px; padding: 0 8px 0 8px; color: #2d3748;
            }
            QPushButton {
                background-color: #2d3748;   
                color: #f8fafc;            
                border: 1px solid #4a5568;
                border-radius: 5px;
                padding: 5px 12px;
            }
            QPushButton:hover {
                background-color: #4a5568;   
            }
            QPushButton:pressed {
                background-color: #1a202c;   
            }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #4299e1; }
        """)
        
        window = SDFToMapConverter()
        window.show()
        
        result = app.exec_()
        
    except Exception as e:
        result = 1
    
    finally:
        sys.exit(result)
