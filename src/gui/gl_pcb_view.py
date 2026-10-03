"""OpenGL 2.1 compatibility renderer and orthographic inspection camera."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QSurfaceFormat
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from src.gui.i18n import tr
from src.gui.theme import tc
from src.models.pcb_scene import Scene, surface


def reference_mesh(scene):
    """Flat glyph meshes use the same depth buffer as the physical PCB."""
    from shapely.geometry import Polygon

    font = QFont("Consolas")
    font.setPixelSize(100)
    triangles = []
    for text, (x, y, z) in scene.labels:
        path = QPainterPath()
        path.addText(0, 0, font, text)
        geometry = Polygon()
        for contour in path.toSubpathPolygons():
            points = [
                (x + p.x() * 0.020, y + p.y() * 0.020 * (1 if z < 0 else -1)) for p in contour
            ]
            if len(points) >= 3:
                geometry = geometry.symmetric_difference(Polygon(points).buffer(0))
        triangles.extend(surface(geometry, z, (0.9, 0.91, 0.84), flip=z < 0))
    return triangles


@dataclass
class Camera:
    yaw: float = -45
    pitch: float = -60
    span: float = 80
    center: np.ndarray = field(default_factory=lambda: np.zeros(3))
    pan: np.ndarray = field(default_factory=lambda: np.zeros(2))
    radius: float = 100

    def rotation(self):
        a, b = math.radians(self.pitch), math.radians(self.yaw)
        rx = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
        rz = np.array([[math.cos(b), -math.sin(b), 0], [math.sin(b), math.cos(b), 0], [0, 0, 1]])
        return rx @ rz

    def fit(self, bounds, width, height):
        lo, hi = np.array(bounds[0]), np.array(bounds[1])
        self.center = (lo + hi) / 2
        self.radius = max(1, float(np.linalg.norm(hi - lo)) / 2)
        corners = np.array(
            [[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
        )
        projected = (corners - self.center) @ self.rotation().T
        extent = np.ptp(projected, axis=0)
        aspect = max(1, width) / max(1, height)
        self.span = max(1, extent[1], extent[0] / aspect) * 1.18
        self.pan[:] = 0

    def zoom(self, factor, pos, width, height):
        old = self.span
        self.span = min(self.radius * 30, max(self.radius * 0.03, self.span / factor))
        # Keep the point under the cursor stationary in camera space.
        normalized = np.array(
            [(pos.x() - width / 2) / max(1, height), -(pos.y() - height / 2) / max(1, height)]
        )
        self.pan += normalized * (old - self.span)

    def project(self, point, width, height):
        p = self.rotation() @ (np.array(point) - self.center)
        p[:2] -= self.pan
        return QPointF(
            width / 2 + p[0] * height / self.span, height / 2 - p[1] * height / self.span
        ), p[2]


class GLPCBView(QOpenGLWidget):
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        fmt = QSurfaceFormat()
        fmt.setVersion(2, 1)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
        fmt.setDepthBufferSize(24)
        fmt.setSamples(4)
        self.setFormat(fmt)
        self.camera = Camera()
        self.scene = Scene()
        self.visible_groups = {"board": True, "pads": True, "components": True, "traces": True}
        self.show_guides = False
        self.show_silk = True
        self.mask_color = None
        self._lists = {}
        self._dirty = True
        self._ready = False
        self._error = False
        self._mouse = None
        self._fit_pending = True
        self.setMinimumSize(200, 180)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_scene(self, scene, *, fit=True):
        self.scene = scene
        self.scene.groups["silk"] = reference_mesh(scene)
        self._dirty = True
        if fit:
            self._fit_pending = True
            self.fit()
        else:
            self.update()

    def fit(self):
        self.camera.fit(self.scene.bounds, self.width(), self.height())
        self.update()

    def preset(self, name):
        self.camera.pitch, self.camera.yaw = {"top": (0, 0), "bottom": (180, 0), "iso": (-60, -45)}[
            name
        ]
        self.fit()

    def zoom(self, factor, pos=None):
        self.camera.zoom(
            factor, pos or QPointF(self.width() / 2, self.height() / 2), self.width(), self.height()
        )
        self.update()

    def initializeGL(self):
        try:
            from OpenGL import GL

            self.gl = GL
            if not GL.glGetString(GL.GL_VERSION):
                raise RuntimeError("No OpenGL context")
            GL.glEnable(GL.GL_DEPTH_TEST)
            GL.glEnable(GL.GL_MULTISAMPLE)
            GL.glEnable(GL.GL_NORMALIZE)
            GL.glEnable(GL.GL_LIGHTING)
            GL.glEnable(GL.GL_LIGHT0)
            GL.glEnable(GL.GL_COLOR_MATERIAL)
            GL.glColorMaterial(GL.GL_FRONT_AND_BACK, GL.GL_AMBIENT_AND_DIFFUSE)
            GL.glLightModeli(GL.GL_LIGHT_MODEL_TWO_SIDE, GL.GL_TRUE)
            GL.glLightModelfv(GL.GL_LIGHT_MODEL_AMBIENT, (0.30, 0.30, 0.30, 1))
            GL.glLightfv(GL.GL_LIGHT0, GL.GL_DIFFUSE, (0.85, 0.85, 0.85, 1))
            GL.glMaterialfv(GL.GL_FRONT_AND_BACK, GL.GL_SPECULAR, (0.18, 0.18, 0.18, 1))
            GL.glMaterialf(GL.GL_FRONT_AND_BACK, GL.GL_SHININESS, 28)
            self._ready = True
            self.context().aboutToBeDestroyed.connect(self.cleanup)
        except Exception as exc:  # noqa: BLE001 -- Qt callbacks must switch to the software renderer.
            self._fail(exc)

    def _fail(self, exc):
        if not self._error:
            self._error = True
            self.failed.emit(str(exc))

    def cleanup(self):
        if self.context() and self.context().isValid():
            self.makeCurrent()
            for handle in self._lists.values():
                self.gl.glDeleteLists(handle, 1)
            self.doneCurrent()
        self._lists.clear()
        self._dirty = True
        self._ready = False

    def _compile(self):
        gl = self.gl
        for handle in self._lists.values():
            gl.glDeleteLists(handle, 1)
        self._lists.clear()
        for name, triangles in self.scene.groups.items():
            handle = gl.glGenLists(1)
            if not handle:
                raise RuntimeError("OpenGL display lists unavailable")
            self._lists[name] = handle
            gl.glNewList(handle, gl.GL_COMPILE)
            gl.glBegin(gl.GL_TRIANGLES)
            for triangle in triangles:
                color = triangle.color
                if name == "board" and abs(triangle.normal[2]) > 0.9 and self.mask_color:
                    color = self.mask_color
                gl.glColor3f(*color)
                gl.glNormal3f(*triangle.normal)
                for point in triangle.vertices:
                    gl.glVertex3f(*point)
            gl.glEnd()
            gl.glEndList()
        self._dirty = False

    def paintGL(self):
        if not self._ready or self._error:
            return
        try:
            gl, cam = self.gl, self.camera
            # QPainter's text pass changes GL state; restore it every frame.
            gl.glEnable(gl.GL_DEPTH_TEST)
            gl.glEnable(gl.GL_LIGHTING)
            gl.glEnable(gl.GL_LIGHT0)
            gl.glEnable(gl.GL_COLOR_MATERIAL)
            gl.glEnable(gl.GL_NORMALIZE)
            gl.glDisable(gl.GL_BLEND)
            if self._fit_pending:
                self.fit()
                self._fit_pending = False
            bg = QColor(tc().scene_bg)
            gl.glClearColor(bg.redF(), bg.greenF(), bg.blueF(), 1)
            gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
            ratio = self.devicePixelRatioF()
            gl.glViewport(0, 0, round(self.width() * ratio), round(self.height() * ratio))
            aspect = self.width() / max(1, self.height())
            half, depth = cam.span / 2, cam.radius * 50
            gl.glMatrixMode(gl.GL_PROJECTION)
            gl.glLoadIdentity()
            gl.glOrtho(-half * aspect, half * aspect, -half, half, -depth, depth)
            gl.glMatrixMode(gl.GL_MODELVIEW)
            gl.glLoadIdentity()
            gl.glLightfv(gl.GL_LIGHT0, gl.GL_POSITION, (-0.3, 0.5, 1, 0))
            gl.glTranslatef(-cam.pan[0], -cam.pan[1], 0)
            gl.glRotatef(cam.pitch, 1, 0, 0)
            gl.glRotatef(cam.yaw, 0, 0, 1)
            gl.glTranslatef(*(-cam.center))
            if self._dirty:
                self._compile()
            for name, handle in self._lists.items():
                if name == "silk" and not self.show_silk:
                    continue
                if self.visible_groups.get(name, True):
                    gl.glCallList(handle)
            gl.glDisable(gl.GL_LIGHTING)
            if self.show_guides:
                gl.glColor3f(0.35, 0.65, 0.85)
                gl.glLineWidth(1)
                gl.glBegin(gl.GL_LINES)
                for a, b in self.scene.guides:
                    gl.glVertex3f(*a)
                    gl.glVertex3f(*b)
                gl.glEnd()
            gl.glEnable(gl.GL_LIGHTING)
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            painter.setPen(QColor(tc().text_dim))
            painter.drawText(12, self.height() - 12, tr("view3d_hint"))
            if not any(self.scene.groups.values()):
                painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr("view3d_empty"))
            painter.end()
        except Exception as exc:  # noqa: BLE001 -- Driver failures must not escape a Qt callback.
            self._fail(exc)

    def mousePressEvent(self, event):
        self._mouse = event.position()

    def mouseMoveEvent(self, event):
        if self._mouse is None:
            return
        d = event.position() - self._mouse
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.camera.yaw += d.x() * 0.5
            self.camera.pitch = (self.camera.pitch + d.y() * 0.5) % 360
        elif event.buttons() & (Qt.MouseButton.RightButton | Qt.MouseButton.MiddleButton):
            self.camera.pan += np.array([-d.x(), d.y()]) * self.camera.span / max(1, self.height())
        self._mouse = event.position()
        self.update()

    def mouseReleaseEvent(self, event):
        self._mouse = None

    def wheelEvent(self, event):
        delta = event.angleDelta().y() or event.pixelDelta().y()
        if delta:
            self.zoom(1.15 ** (delta / 120), event.position())

    def mouseDoubleClickEvent(self, event):
        self.fit()
