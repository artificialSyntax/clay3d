"""GLSL: objects, canvas, lines, fullscreen filter."""

OBJECT_VERTEX = """#version 330 core
layout(location = 0) in vec3 aPosition;
layout(location = 1) in vec3 aNormal;
layout(location = 2) in vec2 aTexCoord;

uniform mat4 uModel;
uniform mat4 uViewProjection;
uniform mat3 uNormalMatrix;

out vec3 vWorld;
out vec3 vNormal;
out vec2 vTexCoord;

void main() {
    vec4 world = uModel * vec4(aPosition, 1.0);
    vWorld = world.xyz;
    vNormal = uNormalMatrix * aNormal;
    vTexCoord = aTexCoord;
    gl_Position = uViewProjection * world;
}
"""

OBJECT_FRAGMENT = """#version 330 core
in vec3 vWorld;
in vec3 vNormal;
in vec2 vTexCoord;

uniform vec3 uEye;
uniform vec4 uColor;
uniform float uSmoothness;
uniform float uMetallic;
uniform sampler2D uTexture;
uniform bool uHasTexture;

// Three lights and an environment colour.
uniform vec3 uLightDirection[3];
uniform vec3 uLightColor[3];
uniform float uLightIntensity[3];
uniform vec3 uEnvironmentColor;
uniform float uEnvironmentIntensity;

out vec4 fragColor;

void main() {
    vec3 n = normalize(vNormal);
    if (!gl_FrontFacing) {
        n = -n;
    }
    vec3 view = normalize(uEye - vWorld);

    vec3 albedo = uColor.rgb;
    if (uHasTexture) {
        vec4 decal = texture(uTexture, vTexCoord);
        albedo = mix(albedo, decal.rgb, decal.a);
    }

    // Environment term, brighter from above than below.
    vec3 lit = albedo * uEnvironmentColor * uEnvironmentIntensity
               * (0.72 + 0.28 * (n.y * 0.5 + 0.5));

    float shininess = mix(12.0, 128.0, clamp(uSmoothness, 0.0, 1.0));
    for (int i = 0; i < 3; ++i) {
        vec3 direction = uLightDirection[i];
        float lambert = max(dot(n, direction), 0.0);
        vec3 contribution = uLightColor[i] * uLightIntensity[i];
        lit += albedo * contribution * lambert;

        vec3 half_vector = normalize(direction + view);
        float specular = pow(max(dot(n, half_vector), 0.0), shininess) * uSmoothness;
        lit += mix(vec3(1.0), albedo, uMetallic) * contribution * specular * 0.7;
    }

    float rim = pow(1.0 - max(dot(n, view), 0.0), 3.0) * 0.08;
    fragColor = vec4(lit + rim, uColor.a);
}
"""

CANVAS_VERTEX = """#version 330 core
layout(location = 0) in vec3 aPosition;
layout(location = 1) in vec2 aTexCoord;

uniform mat4 uViewProjection;

out vec2 vTexCoord;
out vec3 vWorld;

void main() {
    vWorld = aPosition;
    vTexCoord = aTexCoord;
    gl_Position = uViewProjection * vec4(aPosition, 1.0);
}
"""

CANVAS_FRAGMENT = """#version 330 core
in vec2 vTexCoord;
in vec3 vWorld;

uniform sampler2D uCanvas;
uniform vec2 uCheckerScale;

out vec4 fragColor;

void main() {
    vec4 paint = texture(uCanvas, vTexCoord);
    // Transparent paper shows the usual checkerboard underneath.
    vec2 cell = floor(vTexCoord * uCheckerScale);
    float checker = mod(cell.x + cell.y, 2.0);
    vec3 paper = mix(vec3(1.0), vec3(0.85, 0.85, 0.87), checker);
    fragColor = vec4(mix(paper, paint.rgb, paint.a), 1.0);
}
"""

FLAT_VERTEX = """#version 330 core
layout(location = 0) in vec3 aPosition;
uniform mat4 uViewProjection;
void main() {
    gl_Position = uViewProjection * vec4(aPosition, 1.0);
}
"""

FLAT_FRAGMENT = """#version 330 core
uniform vec4 uColor;
out vec4 fragColor;
void main() {
    fragColor = uColor;
}
"""

FILTER_VERTEX = """#version 330 core
layout(location = 0) in vec2 aPosition;
out vec2 vTexCoord;
void main() {
    vTexCoord = aPosition * 0.5 + 0.5;
    gl_Position = vec4(aPosition, 0.0, 1.0);
}
"""

FILTER_FRAGMENT = """#version 330 core
in vec2 vTexCoord;

uniform sampler2D uScene;
uniform float uStrength;

// Colour grade. Each vec3 is (shadows, midtones, highlights).
uniform float uColourFilterHue;      // ColorFilterHueGlobal, in turns
uniform vec3 uColourFilterDensity;   // ColorFilterDensity per band
uniform vec3 uExposure;              // Exposure per band
uniform vec3 uSaturation;            // Saturation per band
uniform float uSaturationGlobal;
uniform float uVignetteWeight;
uniform vec2 uVignetteCentre;

out vec4 fragColor;

vec3 hue_to_rgb(float hue) {
    vec3 p = abs(fract(vec3(hue) + vec3(1.0, 2.0 / 3.0, 1.0 / 3.0)) * 6.0 - 3.0);
    return clamp(p - 1.0, 0.0, 1.0);
}

void main() {
    vec3 source = texture(uScene, vTexCoord).rgb;
    float luma = dot(source, vec3(0.299, 0.587, 0.114));

    // Three overlapping tonal bands, weights summing to one.
    float shadows = 1.0 - smoothstep(0.0, 0.5, luma);
    float highlights = smoothstep(0.5, 1.0, luma);
    float midtones = 1.0 - shadows - highlights;
    vec3 weight = vec3(shadows, midtones, highlights);

    // Colour filter: push each band toward the filter's hue, as densely
    // as that band asks for.
    vec3 filter_colour = hue_to_rgb(uColourFilterHue);
    float density = dot(weight, uColourFilterDensity);
    vec3 graded = mix(source, source * filter_colour * 2.0, density);

    // Exposure, per band, in stops.
    graded *= exp2(dot(weight, uExposure));

    // Saturation, per band and then globally.
    float graded_luma = dot(graded, vec3(0.299, 0.587, 0.114));
    graded = mix(vec3(graded_luma), graded, dot(weight, uSaturation));
    graded_luma = dot(graded, vec3(0.299, 0.587, 0.114));
    graded = mix(vec3(graded_luma), graded, uSaturationGlobal);

    vec3 result = mix(source, clamp(graded, 0.0, 1.0), uStrength);

    if (uVignetteWeight > 0.0) {
        vec2 offset = vTexCoord - uVignetteCentre;
        float fade = 1.0 - uVignetteWeight * dot(offset, offset) * 2.4;
        result *= clamp(fade, 0.0, 1.0);
    }
    fragColor = vec4(result, 1.0);
}
"""
