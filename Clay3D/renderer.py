"""OpenGL draw: MSAA scene → resolve → fullscreen effect pass."""

from __future__ import annotations

import numpy as np
from PySide6.QtGui import QMatrix4x4, QOpenGLFunctions, QVector3D
from PySide6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLFramebufferObject,
    QOpenGLFramebufferObjectFormat,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLTexture,
    QOpenGLVertexArrayObject,
)

from Clay3D import shaders
from Clay3D.effects import EFFECTS

# PySide6 resolves setUniformValue(location, <python float>) to the int
# overload, which GL rejects with INVALID_OPERATION and silently leaves
# the uniform at zero. Scalar floats must go through setUniformValue1f.
GL_FLOAT = 0x1406
GL_TRIANGLES = 0x0004
GL_LINES = 0x0001
GL_DEPTH_TEST = 0x0B71
GL_BLEND = 0x0BE2
GL_SRC_ALPHA = 0x0302
GL_ONE_MINUS_SRC_ALPHA = 0x0303
GL_COLOR_BUFFER_BIT = 0x4000
GL_DEPTH_BUFFER_BIT = 0x0100
GL_TEXTURE_2D = 0x0DE1
GL_TEXTURE0 = 0x84C0
GL_MULTISAMPLE = 0x809D
GL_FRAMEBUFFER = 0x8D40

PIXEL_RGBA = QOpenGLTexture.PixelFormat.RGBA
PIXEL_UINT8 = QOpenGLTexture.PixelType.UInt8

STAGE_BOTTOM = (0.863, 0.878, 0.898)

# Three-light rig and environment colour; amounts live in tuning.py.
from Clay3D.tuning import ENVIRONMENT_COLOR, ENVIRONMENT_INTENSITY, LIGHT_RIG

# Vignette centre, in view fractions.
VIGNETTE_CENTRE = (0.5, 0.5)
# Ground plane opacity.
GROUND_PLANE_OPACITY = 0.4
GRID_COLOR = (0.62, 0.65, 0.69, GROUND_PLANE_OPACITY)


class _Buffer:
    """A vertex array plus its buffer, kept together so they die together."""

    def __init__(self, program: QOpenGLShaderProgram, data: np.ndarray, layout: list[tuple]):
        self.count = len(data)
        self.vao = QOpenGLVertexArrayObject()
        self.vao.create()
        self.vao.bind()
        self.vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self.vbo.create()
        self.vbo.bind()
        packed = np.ascontiguousarray(data, dtype=np.float32)
        self.vbo.allocate(packed.tobytes(), packed.nbytes)
        stride = packed.shape[1] * 4
        program.bind()
        for location, size, offset in layout:
            program.enableAttributeArray(location)
            program.setAttributeBuffer(location, GL_FLOAT, offset * 4, size, stride)
        self.vao.release()
        self.vbo.release()

    def destroy(self) -> None:
        self.vbo.destroy()
        self.vao.destroy()


class SceneRenderer(QOpenGLFunctions):
    def __init__(self) -> None:
        QOpenGLFunctions.__init__(self)
        self.programs: dict[str, QOpenGLShaderProgram] = {}
        self.meshes: dict[int, tuple[_Buffer, int]] = {}
        self.textures: dict[int, tuple[QOpenGLTexture, int]] = {}
        self.canvas_texture: QOpenGLTexture | None = None
        self.canvas_shape = (0, 0)
        self._grid: _Buffer | None = None
        self._canvas_quad: _Buffer | None = None
        self._canvas_extent = (0.0, 0.0)
        self._screen_quad: _Buffer | None = None
        self._multisample: QOpenGLFramebufferObject | None = None
        self._resolved: QOpenGLFramebufferObject | None = None
        self._target_size = (0, 0)
        self.ready = False

    # ---- setup ----------------------------------------------------------

    def initialize(self) -> None:
        self.initializeOpenGLFunctions()
        self.programs["object"] = _compile(shaders.OBJECT_VERTEX, shaders.OBJECT_FRAGMENT)
        self.programs["canvas"] = _compile(shaders.CANVAS_VERTEX, shaders.CANVAS_FRAGMENT)
        self.programs["flat"] = _compile(shaders.FLAT_VERTEX, shaders.FLAT_FRAGMENT)
        self.programs["filter"] = _compile(shaders.FILTER_VERTEX, shaders.FILTER_FRAGMENT)
        self._grid = _Buffer(self.programs["flat"], _grid_lines(), [(0, 3, 0)])
        self._screen_quad = _Buffer(
            self.programs["filter"],
            np.array([[-1, -1], [3, -1], [-1, 3]], dtype=np.float32),
            [(0, 2, 0)],
        )
        self.ready = True

    def release(self) -> None:
        for buffer, _ in self.meshes.values():
            buffer.destroy()
        for texture, _ in self.textures.values():
            texture.destroy()
        self.meshes.clear()
        self.textures.clear()
        if self.canvas_texture is not None:
            self.canvas_texture.destroy()
            self.canvas_texture = None
        for buffer in (self._grid, self._canvas_quad, self._screen_quad):
            if buffer is not None:
                buffer.destroy()
        self._grid = self._canvas_quad = self._screen_quad = None
        self.ready = False

    # ---- textures -------------------------------------------------------

    def _new_texture(self, pixels: np.ndarray) -> QOpenGLTexture:
        height, width = pixels.shape[:2]
        texture = QOpenGLTexture(QOpenGLTexture.Target.Target2D)
        texture.setFormat(QOpenGLTexture.TextureFormat.RGBA8_UNorm)
        texture.setSize(width, height)
        texture.setMipLevels(1)
        texture.setMinMagFilters(
            QOpenGLTexture.Filter.Linear, QOpenGLTexture.Filter.Linear
        )
        texture.setWrapMode(QOpenGLTexture.WrapMode.ClampToEdge)
        texture.allocateStorage(PIXEL_RGBA, PIXEL_UINT8)
        texture.setData(PIXEL_RGBA, PIXEL_UINT8, np.ascontiguousarray(pixels).tobytes())
        return texture

    def sync_canvas(self, canvas, dirty=None) -> None:
        """Upload the canvas, or just the rectangle a tool touched.

        Uploading only the dirty patch is what keeps a brush stroke on a
        large canvas from costing a full texture transfer per mouse move.
        """
        shape = (canvas.height, canvas.width)
        if self.canvas_texture is None or shape != self.canvas_shape:
            if self.canvas_texture is not None:
                self.canvas_texture.destroy()
            self.canvas_texture = self._new_texture(canvas.pixels)
            self.canvas_shape = shape
            return
        if dirty is None:
            dirty = (0, 0, canvas.width, canvas.height)
        x0, y0, x1, y1 = dirty
        patch = np.ascontiguousarray(canvas.pixels[y0:y1, x0:x1])
        self.canvas_texture.setData(
            x0, y0, 0, x1 - x0, y1 - y0, 1, PIXEL_RGBA, PIXEL_UINT8, patch.tobytes()
        )

    def _object_texture(self, obj) -> QOpenGLTexture:
        cached = self.textures.get(id(obj))
        if cached is not None and cached[1] == obj.revision:
            return cached[0]
        if cached is not None:
            cached[0].destroy()
        texture = self._new_texture(obj.texture)
        self.textures[id(obj)] = (texture, obj.revision)
        return texture

    # ---- geometry -------------------------------------------------------

    def _mesh_buffer(self, obj) -> _Buffer:
        key = id(obj)
        cached = self.meshes.get(key)
        if cached is not None and cached[1] == obj.mesh.vertex_count:
            return cached[0]
        if cached is not None:
            cached[0].destroy()
        buffer = _Buffer(
            self.programs["object"],
            obj.mesh.interleaved(),
            [(0, 3, 0), (1, 3, 3), (2, 2, 6)],
        )
        self.meshes[key] = (buffer, obj.mesh.vertex_count)
        return buffer

    def _canvas_buffer(self, scene) -> _Buffer:
        extent = scene.canvas_extent()
        if self._canvas_quad is not None and extent == self._canvas_extent:
            return self._canvas_quad
        if self._canvas_quad is not None:
            self._canvas_quad.destroy()
        half_w, half_h = extent
        data = np.array(
            [
                [-half_w, -half_h, 0, 0, 1],
                [half_w, -half_h, 0, 1, 1],
                [half_w, half_h, 0, 1, 0],
                [-half_w, -half_h, 0, 0, 1],
                [half_w, half_h, 0, 1, 0],
                [-half_w, half_h, 0, 0, 0],
            ],
            dtype=np.float32,
        )
        self._canvas_quad = _Buffer(self.programs["canvas"], data, [(0, 3, 0), (1, 2, 3)])
        self._canvas_extent = extent
        return self._canvas_quad

    # ---- drawing --------------------------------------------------------

    def _ensure_targets(self, width: int, height: int) -> None:
        if self._multisample is not None and self._target_size == (width, height):
            return
        multisampled = QOpenGLFramebufferObjectFormat()
        multisampled.setSamples(4)
        multisampled.setAttachment(QOpenGLFramebufferObject.Attachment.Depth)
        self._multisample = QOpenGLFramebufferObject(width, height, multisampled)
        plain = QOpenGLFramebufferObjectFormat()
        plain.setSamples(0)
        self._resolved = QOpenGLFramebufferObject(width, height, plain)
        self._target_size = (width, height)

    def render(self, scene, width: int, height: int, default_fbo: int, overlays=()) -> None:
        width, height = max(1, width), max(1, height)
        self._ensure_targets(width, height)

        self._multisample.bind()
        self.glViewport(0, 0, width, height)
        self.glEnable(GL_MULTISAMPLE)
        self._draw_stage_background()
        self.glEnable(GL_DEPTH_TEST)
        self.glEnable(GL_BLEND)
        self.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        view_projection = _matrix(scene.camera.view_projection(width, height))
        if scene.show_grid and scene.camera.mode == "orbit":
            self._draw_grid(view_projection)
        if scene.show_canvas:
            self._draw_canvas(scene, view_projection)
        self._draw_objects(scene, view_projection)
        for overlay in overlays:
            overlay(self, view_projection)
        self._multisample.release()

        QOpenGLFramebufferObject.blitFramebuffer(self._resolved, self._multisample)

        self.glBindFramebuffer(GL_FRAMEBUFFER, default_fbo)
        self.glViewport(0, 0, width, height)
        self.glDisable(GL_DEPTH_TEST)
        self._apply_filter(scene)

    def _draw_stage_background(self) -> None:
        self.glDisable(GL_DEPTH_TEST)
        self.glClearColor(*STAGE_BOTTOM, 1.0)
        self.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

    def _draw_grid(self, view_projection: QMatrix4x4) -> None:
        program = self.programs["flat"]
        program.bind()
        program.setUniformValue(program.uniformLocation("uViewProjection"), view_projection)
        program.setUniformValue(program.uniformLocation("uColor"), *GRID_COLOR)
        self._grid.vao.bind()
        self.glDrawArrays(GL_LINES, 0, self._grid.count)
        self._grid.vao.release()

    def _draw_canvas(self, scene, view_projection: QMatrix4x4) -> None:
        if self.canvas_texture is None:
            self.sync_canvas(scene.canvas)
        program = self.programs["canvas"]
        program.bind()
        program.setUniformValue(program.uniformLocation("uViewProjection"), view_projection)
        program.setUniformValue(program.uniformLocation("uCanvas"), 0)
        checker = max(8.0, scene.canvas.width / 24.0)
        program.setUniformValue(
            program.uniformLocation("uCheckerScale"),
            float(checker),
            float(checker * scene.canvas.height / max(scene.canvas.width, 1)),
        )
        self.canvas_texture.bind(0)
        buffer = self._canvas_buffer(scene)
        buffer.vao.bind()
        self.glDrawArrays(GL_TRIANGLES, 0, buffer.count)
        buffer.vao.release()

    def _draw_objects(self, scene, view_projection: QMatrix4x4) -> None:
        if not scene.objects:
            return
        program = self.programs["object"]
        program.bind()
        program.setUniformValue(program.uniformLocation("uViewProjection"), view_projection)
        eye = scene.camera.eye()
        program.setUniformValue(
            program.uniformLocation("uEye"), QVector3D(*[float(v) for v in eye])
        )
        for index, (direction, colour, intensity) in enumerate(_light_rig(scene.light_rotation)):
            program.setUniformValue(
                program.uniformLocation(f"uLightDirection[{index}]"), QVector3D(*direction)
            )
            program.setUniformValue(
                program.uniformLocation(f"uLightColor[{index}]"), QVector3D(*colour)
            )
            program.setUniformValue1f(
                program.uniformLocation(f"uLightIntensity[{index}]"), float(intensity)
            )
        program.setUniformValue(
            program.uniformLocation("uEnvironmentColor"), QVector3D(*ENVIRONMENT_COLOR)
        )
        program.setUniformValue1f(
            program.uniformLocation("uEnvironmentIntensity"), ENVIRONMENT_INTENSITY
        )

        for obj in scene.objects:
            model = _matrix(obj.transform.matrix())
            program.setUniformValue(program.uniformLocation("uModel"), model)
            program.setUniformValue(
                program.uniformLocation("uNormalMatrix"), model.normalMatrix()
            )
            r, g, b, a = obj.color
            program.setUniformValue(
                program.uniformLocation("uColor"), r / 255.0, g / 255.0, b / 255.0, a / 255.0
            )
            program.setUniformValue1f(
                program.uniformLocation("uSmoothness"), float(obj.smoothness)
            )
            program.setUniformValue1f(
                program.uniformLocation("uMetallic"), float(obj.metallic)
            )
            has_texture = obj.texture is not None
            program.setUniformValue(program.uniformLocation("uHasTexture"), has_texture)
            if has_texture:
                self._object_texture(obj).bind(0)
                program.setUniformValue(program.uniformLocation("uTexture"), 0)
            buffer = self._mesh_buffer(obj)
            buffer.vao.bind()
            self.glDrawArrays(GL_TRIANGLES, 0, buffer.count)
            buffer.vao.release()

    def _apply_filter(self, scene) -> None:
        effect = EFFECTS.get(scene.effect, EFFECTS["none"])
        program = self.programs["filter"]
        program.bind()
        program.setUniformValue(program.uniformLocation("uScene"), 0)
        program.setUniformValue1f(
            program.uniformLocation("uStrength"), float(effect.strength)
        )
        program.setUniformValue1f(
            program.uniformLocation("uColourFilterHue"), float(effect.colour_filter_hue)
        )
        program.setUniformValue(
            program.uniformLocation("uColourFilterDensity"), *effect.colour_filter_density
        )
        program.setUniformValue(program.uniformLocation("uExposure"), *effect.exposure)
        program.setUniformValue(program.uniformLocation("uSaturation"), *effect.saturation)
        program.setUniformValue1f(
            program.uniformLocation("uSaturationGlobal"), float(effect.saturation_global)
        )
        program.setUniformValue1f(
            program.uniformLocation("uVignetteWeight"), float(effect.vignette_weight)
        )
        program.setUniformValue(program.uniformLocation("uVignetteCentre"), *VIGNETTE_CENTRE)
        self.glActiveTexture(GL_TEXTURE0)
        self.glBindTexture(GL_TEXTURE_2D, self._resolved.texture())
        self._screen_quad.vao.bind()
        self.glDrawArrays(GL_TRIANGLES, 0, 3)
        self._screen_quad.vao.release()

    def draw_lines(self, points: np.ndarray, color, view_projection, width: float = 1.0) -> None:
        """A one-off line list, used for selection boxes drawn in world space."""
        program = self.programs["flat"]
        program.bind()
        program.setUniformValue(program.uniformLocation("uViewProjection"), view_projection)
        program.setUniformValue(program.uniformLocation("uColor"), *color)
        buffer = _Buffer(program, points.astype(np.float32), [(0, 3, 0)])
        self.glLineWidth(width)
        buffer.vao.bind()
        self.glDrawArrays(GL_LINES, 0, buffer.count)
        buffer.vao.release()
        buffer.destroy()


def _compile(vertex_source: str, fragment_source: str) -> QOpenGLShaderProgram:
    program = QOpenGLShaderProgram()
    if not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, vertex_source):
        raise RuntimeError(f"vertex shader failed: {program.log()}")
    if not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, fragment_source):
        raise RuntimeError(f"fragment shader failed: {program.log()}")
    if not program.link():
        raise RuntimeError(f"shader link failed: {program.log()}")
    return program


def _matrix(array: np.ndarray) -> QMatrix4x4:
    """numpy 4x4 to Qt, which takes its 16 floats row by row."""
    return QMatrix4x4(*[float(v) for v in np.asarray(array, dtype=float).flatten()])


def _light_rig(rotation: float):
    """Key, fill opposite it, rim from behind. Turns with the lighting dial."""
    lights = []
    for offset, colour, intensity, height in LIGHT_RIG:
        angle = float(rotation) + offset
        direction = np.array([np.sin(angle), height, np.cos(angle)])
        direction = direction / np.linalg.norm(direction)
        lights.append(([float(v) for v in direction], colour, intensity))
    return lights



def _grid_lines(half: int = 8, step: float = 0.5) -> np.ndarray:
    """A floor grid under the scene, sitting just below the canvas."""
    y = -2.2
    reach = half * step
    points = []
    for i in range(-half, half + 1):
        offset = i * step
        points.extend([[-reach, y, offset], [reach, y, offset]])
        points.extend([[offset, y, -reach], [offset, y, reach]])
    return np.array(points, dtype=np.float32)
