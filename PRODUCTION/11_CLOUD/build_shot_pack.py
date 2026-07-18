#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор промпт-пака «Пляж» для облачного рендера (ComfyUI на Colab/Kaggle).

ВЕРСИЯ 2 — полноценная короткометражка ~5.5 минут (вместо прежних 123 c).
Собирает shots_arcane.json: на каждый план — английский промпт ключевого кадра,
motion-промпт для image-to-video, негативы и правила подстановки лиц
(Джон / Мэри / оба / без лиц — детали и силуэты).

Запуск:  python3 build_shot_pack.py
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "shots_arcane.json")
FPS = 24
SEED_BASE = 73137
SEED_STEP = 137

# --------------------------------------------------------------------------
# Общие блоки (из M1_8GB_FACE_ID_ARCANE_GUIDE_RU.md, разделы 6-8)
# --------------------------------------------------------------------------

STYLE_BASE = (
    "painterly hand-painted 2D brush textures over sculpted forms, "
    "visible controlled brush strokes, mature cinematic atmosphere, "
    "deep teal shadows, warm amber highlights, subtle magenta accents, "
    "volumetric sea mist, cinematic composition, restrained color palette, "
    "shallow depth of field, 35mm film language, prestige animated drama"
)

STYLE_CHARACTER = (
    "painterly 3D character design, expressive angular facial planes, "
    "sculpted facial features, detailed expressive eyes, coherent anatomy, "
    "clearly adult characters"
)

ID_SINGLE = (
    "preserve the recognizable facial identity from the attached reference images, "
    "same face shape, same eye shape and spacing, same eyebrows, same nose, "
    "same lips, same jawline, same apparent adult age, "
    "stylized but unmistakably the same person"
)

ID_PAIR = (
    "preserve two separate recognizable adult identities, "
    "the woman keeps only the woman's reference identity, "
    "the man keeps only the man's reference identity, "
    "never blend or exchange their facial features, "
    "same face shapes, eyes, noses, lips, jawlines and apparent ages"
)

NEG_IMAGE = (
    "different person, wrong identity, generic face, identity drift, mixed identities, "
    "blended faces, swapped faces, changed facial proportions, changed apparent age, "
    "teenager, child, minor, baby face, face asymmetry, crossed eyes, mismatched eyes, "
    "deformed eyes, deformed nose, warped mouth, broken jaw, double face, duplicate head, "
    "extra person, cloned person, bad anatomy, extra arms, extra hands, extra fingers, "
    "fused fingers, malformed hands, photorealistic live action, glossy plastic CGI, "
    "flat anime, chibi, childish proportions, oversaturated, washed out, overexposed, "
    "underexposed, low detail, blurry, jpeg artifacts, text, subtitles, watermark, logo, "
    "explicit nudity, sexual act, blue hair, pink hair, green hair, neon hair, "
    "league of legends character, jinx, vi, caitlyn, video game character, "
    "fantasy costume, steampunk goggles, tattoos on face"
)

NEG_NO_PEOPLE = (
    "person, people, woman, man, girl, human, face, portrait, character, "
    "figure, silhouette of a person, crowd, hands, body"
)

NEG_VIDEO = (
    "wrong identity, identity drift, face morphing, face blending, swapped faces, "
    "changed face shape, changed eyes, changed nose, changed mouth, changed apparent age, "
    "teenager, child, minor, melting face, unstable face, asymmetric eyes, "
    "mouth deformation, excessive lip movement, speaking, lip sync, open mouth distortion, "
    "duplicate person, extra person, cloned face, hairstyle change, hair color change, "
    "costume change, bad anatomy, extra limbs, missing limbs, extra fingers, fused fingers, "
    "malformed hands, flicker, temporal jitter, frame warping, camera teleport, sudden cut, "
    "reverse movement, unstable background, impossible reflections, static frozen frame, "
    "low detail, blurry, text, subtitles, watermark, logo, photorealistic live action, "
    "glossy plastic CGI, flat anime, chibi, explicit nudity, sexual act"
)

ID_HOLD_VIDEO = (
    "preserve the exact facial identities from the input frame, same face shapes, "
    "same eyes, same noses, same lips, same jawlines, same apparent adult ages, "
    "never blend or swap their identities, same hairstyles and costumes, "
    "subtle natural facial acting, no speaking and no lip-sync motion, "
    "stable faces, stable background, coherent anatomy"
)

TASTEFUL = (
    "tasteful non-explicit romantic framing, bodies fully concealed by dark water, "
    "shadow and silhouette, only heads, shoulders and upper backs visible, "
    "no explicit nudity, clearly adult characters"
)

LOOK_MARY = (
    "MARY: clearly adult woman with light skin, long dark brown slightly wavy hair, "
    "green-hazel almond-shaped eyes, soft full lips, delicate natural beauty, "
    "short sleeveless deep-teal wrap dress"
)
LOOK_JOHN = (
    "JOHN: clearly adult man, tousled wavy dark-blond curls, blue-grey eyes, "
    "light stubble, athletic build, off-white cotton shirt with rolled sleeves "
    "and sand-colored shorts"
)

FRAME_GUARD = "16:9 cinematic composition, no text, no watermark"


def composition_anchor(shot_size):
    """Return one explicit camera/composition anchor for every size in SHOTS."""
    if "двухплан" in shot_size:
        return "two-shot, both subjects visible in frame"

    anchors = {
        "общий": (
            "extreme wide establishing landscape shot, camera far from subject, "
            "vast open space"
        ),
        "очень общий": (
            "extreme wide establishing landscape shot, camera far from subject, "
            "vast open space"
        ),
        "общий силуэт": "wide backlit silhouette shot, subject small in frame",
        "средний": "medium shot, waist up, subject centered",
        "средний силуэт": "medium backlit silhouette shot, waist up, subject centered",
        "крупный": "close-up shot of a face, head and shoulders only",
        "силуэтный крупный": (
            "close-up backlit silhouette shot, head and shoulders only"
        ),
        "макро": "extreme macro detail shot, object fills the frame, no people, no faces",
        "деталь": "extreme macro detail shot, object fills the frame, no people, no faces",
        "верхний": "top-down overhead shot, camera directly above the subject",
    }
    try:
        return anchors[shot_size]
    except KeyError as exc:
        raise ValueError("Нет композиционного якоря для крупности: %s" % shot_size) from exc


def use_no_people_negative(who, non_explicit_water_scene, shot_size):
    return (
        who == "none"
        and not non_explicit_water_scene
        and shot_size in {"макро", "деталь", "общий"}
    )

# --------------------------------------------------------------------------
# ПОКАДРОВЫЙ ПЛАН — 8 актов, ~5.5 минуты
# who: mary | john | both | none      faces: подставлять ли лица (InstantID)
# t: длительность в секундах          tasteful: неэксплицитная водная/интимная сцена
# --------------------------------------------------------------------------

SHOTS = [
# ---------------------- АКТ 1. Одиночество и закат ----------------------
("Закат", "общий", "very slow push-in", 7.0, "none", False, False,
 "wide establishing shot of a quiet empty Mediterranean beach in the final minutes of sunset, the sun touching the horizon, pale sand, gentle surf, a distant closed beach bar, warm amber light, very long shadows",
 "Slow gentle waves roll in, warm light particles drift in the air, the camera performs a very slow stable push-in toward the shore."),

("Закат", "общий", "static wide", 5.0, "none", False, False,
 "wide shot of a small group of young people walking away from the beach toward distant town lights, seen from behind at a distance, laughing, leaving one lone figure seated on a chaise far behind them",
 "The group walks away into the distance and their silhouettes shrink, dust and light glimmer, the lone figure stays motionless. Locked-off camera."),

("Закат", "средний", "slow lateral drift right", 6.0, "mary", True, False,
 "medium shot of MARY sitting sideways alone on a wooden beach chaise near the sea, holding a bright fruit cocktail, calm expression with a trace of loneliness, evening sea behind her",
 "Her hair and dress move gently in the sea breeze, she slowly exhales and relaxes into the chaise, her fingers turn the chilled glass slightly. Very slow lateral drift to the right."),

("Закат", "крупный", "slow push-in", 5.0, "mary", True, False,
 "close-up of MARY watching the waves, serene and unhurried, the amber sunset painting a warm rim on her cheek and hair, deep teal shadows behind",
 "One slow blink, a barely visible peaceful half-smile, hair moves in the breeze. Very slow push-in. No speaking."),

("Закат", "макро", "macro push-in", 4.0, "none", False, False,
 "extreme macro of a chilled bright fruit cocktail glass with a small paper umbrella, heavy condensation, amber sunset backlight glowing through the red liquid",
 "A single condensation droplet slowly runs down the glass, highlights shimmer through the liquid, slow macro push-in."),

("Закат", "деталь", "locked macro", 4.0, "none", False, False,
 "detail of warm evening surf sliding over pale wet sand, foam edges catching amber light, tiny shells and glitter in the sand",
 "Foam advances and retreats over the sand, light glitters on the wet surface. Locked-off camera."),

("Закат", "крупный", "very slow push-in", 5.0, "mary", True, False,
 "close-up of MARY closing her eyes and breathing in the sea air, shoulders dropping, finally at peace alone, silver-amber transitional light",
 "She closes her eyes and takes one deep slow breath, her shoulders drop, a strand of hair crosses her face. Very slow push-in. No speaking."),

# ---------------------- АКТ 2. Появление Джона ----------------------
("Встреча", "общий", "smooth track left", 6.0, "john", True, False,
 "cinematic full-body shot of JOHN walking barefoot along warm wet sand at the water's edge, sandals hanging from one hand, relaxed confident posture, evening sea behind him, warm sunset rim light",
 "He walks naturally at a relaxed pace, small waves reach his bare feet, his curls move in the breeze. The camera tracks beside him smoothly to the left."),

("Встреча", "деталь", "low tracking macro", 4.0, "none", False, False,
 "low detail shot of bare male feet stepping through warm wet sand, shallow water washing over them, footprints filling with amber-lit water",
 "The feet step forward through the shallow water, footprints fill and dissolve, foam swirls. The camera tracks low beside them."),

("Встреча", "средний", "slow drift", 5.0, "john", True, False,
 "medium shot of JOHN pausing to admire the soft evening waves, calm appreciative expression, golden light on his face and shoulders",
 "He slows and looks out at the sea, the breeze lifts his curls, a small content smile. Slow drift. No speaking."),

("Встреча", "крупный", "slow push-in", 5.0, "mary", True, False,
 "close-up of MARY following someone with her gaze over the rim of her cocktail glass, unhurried curious interest, warm amber rim light",
 "Only her eyes track slowly across the frame, one slow blink, the hint of an amused smile. Very slow push-in. No head rotation greater than ten degrees."),

("Встреча", "двухплановый", "rack focus", 6.5, "both", True, False,
 "cinematic sunset beach two-shot, MARY seated near the sea and JOHN standing several meters away meet each other's gaze for the first time, restrained curiosity and mutual attraction, warm amber backlight, sea mist",
 "He slows for one beat and turns only his eyes toward her, she holds his gaze instead of looking away. A subtle rack focus moves from him to her and holds."),

("Встреча", "крупный", "minimal drift", 5.0, "john", True, False,
 "close-up of JOHN holding his gaze a moment too long, entirely unembarrassed, a quiet spark of interest starting behind his blue-grey eyes",
 "He holds the look, one slow blink, the corner of his mouth lifts slightly. Minimal drift. No speaking."),

("Встреча", "деталь", "macro push-in", 5.0, "none", False, False,
 "macro detail of cold droplets running from a cocktail glass down a woman's hand and forearm onto her thigh, elegant fingers holding the glass, amber backlight through the condensation",
 "Cold droplets slide down the glass onto the hand and thigh, light refracts through them. Slow macro push-in."),

("Встреча", "средний", "pan right", 5.0, "john", True, False,
 "medium shot of JOHN turning away decisively and heading toward a small beach bar, sudden purpose in his stride, blue hour beginning at the horizon",
 "He turns away and walks off with new purpose, sand shifting under his feet. The camera pans right following him."),

# ---------------------- АКТ 3. Бар ----------------------
("Бар", "средний", "pan right", 5.0, "john", True, False,
 "medium shot of JOHN arriving at a small wooden beach bar, amber lamps switching on above the counter, warm pools of light against the deepening blue evening",
 "He arrives and leans one hand on the counter, amber lamps flicker on softly. The camera pans right with him."),

("Бар", "средний", "slow drift", 4.5, "none", False, False,
 "medium shot of a calm bartender behind a wooden beach bar counter unhurriedly polishing glasses, warm amber lamps, bottles glowing behind him, face turned away in soft focus",
 "He keeps polishing a glass with steady circular motion, lamplight glints on the glassware. Slow drift."),

("Бар", "деталь", "slow push-in", 5.0, "none", False, False,
 "detail shot of two identical bright fruit cocktails placed on a polished bar counter, small paper umbrellas, ice, heavy condensation, warm amber lamps, dark teal evening behind",
 "Ice settles slightly, liquid and bubbles move, fresh condensation forms on the glass. Slow push-in toward the two glasses."),

("Бар", "крупный", "slow push-in", 5.0, "john", True, False,
 "close-up of JOHN checking his reflection in the curved surface of a cocktail glass and smoothing his curls back, amused confident half-smile, amber bar light on his face",
 "He runs a hand once through his curls and studies his warped reflection, a small confident smile appears. Slow push-in."),

("Бар", "макро", "locked macro", 4.0, "none", False, False,
 "macro of careful male fingers straightening a tiny paper cocktail umbrella in a glass, condensation, warm amber highlights, a moment of deliberate care",
 "The fingers adjust the small umbrella precisely and withdraw, the liquid sways. Locked-off macro."),

("Бар", "средний", "track backward", 5.0, "john", True, False,
 "medium tracking shot of JOHN walking back across the darkening sand carrying two cocktails, one in each hand, quiet determination and anticipation on his face, first stars above",
 "He walks steadily toward camera carrying both glasses level, liquid swaying gently, evening light fading to blue. The camera tracks backward ahead of him."),

# ---------------------- АКТ 4. Знакомство ----------------------
("Знакомство", "крупный", "quick settle then hold", 5.0, "mary", True, False,
 "close-up of MARY startled, turning sharply toward a sound at her left, eyes wide with surprise, a small gasp, amber and teal evening light",
 "She startles and turns her head quickly toward the sound, eyes widening, then freezes. The camera settles and holds. No speaking."),

("Знакомство", "двухплановый", "slow lateral drift left", 6.5, "both", True, False,
 "intimate cinematic medium two-shot on the twilight beach, JOHN offers a chilled fruit cocktail to MARY seated on the chaise, his arm extended holding the glass with two fingers, respectful distance, guarded but amused expressions, two matching transparent glasses",
 "He extends one cocktail glass slowly toward her, she draws back for a brief startled moment then looks up at his face. The glass keeps its shape and the liquid moves naturally. Gentle lateral drift left."),

("Знакомство", "крупный", "slow push-in", 5.0, "john", True, False,
 "close-up of JOHN smiling warmly from behind the raised cocktail glass, damp curls swept back, blue-grey eyes the colour of the evening sky, open friendly apology on his face",
 "He tilts his head slightly and his smile widens, curls shifting in the breeze. Slow push-in. Lips almost still for later voice-over."),

("Знакомство", "крупный", "minimal drift", 5.0, "mary", True, False,
 "close-up of MARY answering with polite guarded refusal, one eyebrow slightly raised, recognizing the man who walked past earlier, cool amusement in her green-hazel eyes",
 "A small guarded smile, one eyebrow lifts, she studies his face with growing recognition. Minimal drift. No speaking."),

("Знакомство", "двухплановый", "slow arc", 6.0, "both", True, False,
 "two-shot at blue hour, JOHN gesturing easily toward the view, relaxed and not insisting at all, MARY watching him with softening surprise at his easy manner",
 "He gestures once toward the sea and shrugs lightly without pressure, she watches and her guarded expression softens. Small slow arc of the camera."),

("Знакомство", "средний", "slow push-in", 5.0, "both", True, False,
 "medium two-shot, MARY shifting to make room on the chaise and nodding to JOHN, an invitation without words, first stars appearing above the darkening sea",
 "She shifts slightly on the chaise and nods, he begins to sit down beside her. Slow push-in."),

("Знакомство", "макро", "locked macro", 4.0, "none", False, False,
 "locked macro of two cocktail glasses meeting in a toast, condensation, amber highlights refracting through the bright liquid, deep dusk colours behind",
 "The glasses meet once with a bright clear ring, concentric ripples cross the liquid, highlights scatter outward. Locked-off camera."),

("Знакомство", "средний", "small slow arc", 6.0, "both", True, False,
 "medium shot of MARY and JOHN both settled on the wooden chaise facing the sea, comfortable new closeness, two cocktails in hand, the empty darkening beach around them",
 "The sea breeze moves their hair, they exchange one brief glance and small restrained smiles, the light shifts toward blue hour. Small slow arc."),

# ---------------------- АКТ 5. Музыка и разговор ----------------------
("Музыка", "крупный", "slow push-in", 5.0, "mary", True, False,
 "close-up of MARY deliberately turning her face toward JOHN and lifting a strand of hair behind her ear, revealing a small white earbud she has been listening to all along, playful conspiratorial look",
 "She turns her face toward him and tucks a strand of hair behind her ear, revealing the earbud, then raises her eyebrows in invitation. Slow push-in."),

("Музыка", "двухплановый", "very slow push-in", 6.0, "both", True, False,
 "intimate medium close-up of MARY offering one small white earbud to JOHN at blue hour, their fingers almost touching, subtle mutual surprise and warm restrained smiles",
 "She holds out the earbud and he leans slightly closer and takes it carefully, their fingers almost touch. Very slow stable push-in."),

("Музыка", "макро", "locked macro", 4.5, "none", False, False,
 "macro of two hands passing a tiny white earbud between them, fingertips nearly touching, thin cable catching silver moonlight, deep teal background",
 "The earbud passes between the fingertips which almost but never quite touch, the cable sways. Locked-off macro."),

("Музыка", "крупный", "light lateral drift", 5.0, "both", True, False,
 "close two-shot, both wearing one earbud each, the delighted shock of recognizing the same beloved band, his eyebrows raised in disbelief, her teasing proud smile",
 "His eyebrows shoot up in recognition and he laughs silently, she smiles with teasing pride. Light lateral drift. Smiles without lip-sync."),

("Разговор", "средний", "very slow lateral slide", 6.0, "both", True, False,
 "medium shot of MARY and JOHN talking on the chaise as the sky turns deep blue, the last amber band on the horizon, first stars, relaxed open body language, two half-empty glasses",
 "They sit side by side listening, exchange one brief glance and small restrained smiles, the breeze moves their hair and light shifts to blue hour. Very slow lateral slide."),

("Разговор", "крупный", "slow drift", 4.5, "mary", True, False,
 "close-up of MARY drinking the last of her cocktail through a thin paper straw, eyes half-lowered, relaxed and unguarded now, silver-blue evening light",
 "She draws on the straw and lowers the glass, a slow satisfied blink, hair moving in the breeze. Slow drift."),

("Разговор", "макро", "macro push-in", 5.0, "none", False, False,
 "macro detail of a single droplet falling from a paper straw onto an elegant collarbone and beginning to travel slowly downward, warm skin, silver-teal rim light, tasteful framing above the neckline",
 "The droplet falls, lands on the collarbone and begins a slow shining descent, skin catching the light. Slow macro push-in."),

("Разговор", "крупный", "rack focus", 5.0, "both", True, False,
 "close two-shot, JOHN caught looking and lifting his eyes to meet MARY's, her striking green-hazel gaze catching him directly, a charged suspended beat between them",
 "He lifts his eyes and meets hers directly, both hold the look, a held breath between them. Subtle rack focus between the two faces."),

("Разговор", "макро", "locked macro", 4.5, "mary", True, False,
 "extreme macro of MARY's green-hazel eyes with the reflection of the moonlit sea in them, individual lashes, painterly iris texture, deep teal and silver",
 "The reflected light waves move slowly across the iris, one slow blink. Locked-off camera, no head movement."),

# ---------------------- АКТ 6. Пляж опустел ----------------------
("Синий час", "общий", "slow pull-out", 6.0, "none", False, False,
 "wide blue-hour composition, the beach bar's last amber lamp goes dark in the distance, the shore completely empty, two small distant figures on a chaise, the moon rising over the sea",
 "The last amber lamp fades out, the moon rises a little higher, waves roll in steadily. Slow stable pull-out revealing the empty beach."),

("Синий час", "крупный", "slow half-orbit", 5.0, "mary", True, False,
 "close-up of MARY noticing the silence and the completely empty beach, delighted mischievous realization that they are alone, silver moonlight on her face",
 "She looks slowly around the empty shore and a mischievous half-smile grows. Slow half-orbit around her."),

("Синий час", "средний", "slow drift", 5.0, "john", True, False,
 "medium shot of JOHN looking around the deserted moonlit beach as if surfacing from deep water, quiet astonishment at how dark and empty it has become",
 "He looks around slowly, blinking as if waking, then back toward her. Slow drift."),

("Синий час", "общий", "slow tilt up", 5.0, "none", False, False,
 "wide night composition of a huge silver moon rising over a calm dark sea, a shimmering path of moonlight across the water, deep teal sky, scattered stars",
 "The moonlight path shimmers and shifts on the water, clouds drift slowly past the moon. Slow tilt up."),

("Приглашение", "средний", "slow push-in", 6.0, "john", True, False,
 "medium shot of JOHN standing and slowly unbuttoning his cotton shirt, gesturing toward the dark sea with a warm daring smile, silver moonlight rim on his shoulders",
 "He rises, slowly unbuttons the shirt and gestures once toward the water with an inviting confident smile. Slow push-in."),

("Приглашение", "крупный", "minimal drift", 5.0, "mary", True, False,
 "close-up of MARY laughing and protesting playfully, one hand raised, delighted and scandalized at the same time, silver moonlight and deep teal shadow",
 "She laughs silently and raises one hand in playful protest, shaking her head, eyes bright. Minimal drift."),

# ---------------------- АКТ 7. Ночное море ----------------------
("Приглашение", "общий силуэт", "track from behind", 5.0, "none", False, True,
 "wide backlit silhouette from behind of a clearly adult man walking into the dark moonlit sea, seen only as a dark silhouette against silver water, shirt left behind on the chaise",
 "The silhouette walks steadily into the water, splashes catching moonlight. The camera tracks from behind. The figure stays a dark silhouette."),

("Решение", "средний", "push-in then drift", 5.5, "mary", True, False,
 "medium shot of MARY standing alone by the chaise, deciding, wind in her hair and dress, moonlit sea behind her, hesitation resolving into brave excitement",
 "Wind moves her hair and dress, hesitation crosses her face and resolves into a decisive smile, she takes one step toward the sea. Push-in then gentle drift."),

("Решение", "общий силуэт", "track from behind", 5.0, "none", False, True,
 "wide backlit silhouette of a clearly adult woman running toward the dark moonlit sea, seen only as a graceful dark silhouette against silver water, her dress left behind on the sand",
 "The silhouette runs toward the water with light quick steps. The camera tracks from behind. The figure remains a dark silhouette."),

("Решение", "средний силуэт", "water level", 5.0, "none", False, True,
 "dark silhouette of a clearly adult woman diving into the moonlit sea, a clean arc of splash and silver droplets, body concealed by night water and shadow",
 "The silhouette dives and vanishes into the water, a crown of silver droplets rises and falls. The camera holds at water level."),

("Ночное море", "очень общий", "water-level push-in", 6.5, "none", False, True,
 "very wide cinematic night ocean under a silver moon, two clearly adult people swimming several meters apart, only heads, shoulders and upper backs above dark blue water, starry sky, teal mist",
 "The two adult silhouettes swim slowly through gentle moonlit waves, soft ripples and silver splashes move naturally. The camera floats at water level and advances very slowly."),

("Ночное море", "верхний", "slow rotation", 6.5, "mary", True, True,
 "poetic overhead shot of MARY floating peacefully on her back beneath a vast starry sky, face, neck and shoulders above dark moonlit water, calm wonder, cosmic weightless feeling, silver reflections",
 "She floats weightlessly, water moves gently around her, stars shimmer above. Slow small rotation of the camera above her. Serene, no sudden movement."),

("Ночное море", "крупный", "quick turn then hold", 5.0, "mary", True, True,
 "close moonlit shot of MARY turning sharply in chest-deep dark water, startled by a light touch at her waist, goosebumps and quickened breath, silver rim light on wet shoulders",
 "She turns sharply and draws back slightly, eyes wide, breath quickening, water swirling around her shoulders. The camera settles and holds."),

("Ночное море", "средний", "slow push-in", 5.5, "both", True, True,
 "intimate moonlit water-level two-shot, JOHN close to MARY in chest-deep dark water, running both hands back through his wet hair, the movement tensing his shoulders, intense tender eye contact",
 "He runs both hands slowly back through his wet hair and water streams down, she watches him. Water parallax and ripples. Slow push-in."),

("Ночное море", "крупный", "minimal drift", 5.0, "both", True, True,
 "close moonlit two-shot in chest-deep water, held tension and respectful distance between two clearly adult people, silver rim light on wet shoulders, light sea mist, charged suspended air",
 "Minimal drift, held eye contact, visible breathing, water moving around their shoulders. Subtle micro-expressions only."),

# ---------------------- АКТ 8. Доверие и финал ----------------------
("Доверие", "деталь", "slow arc", 5.0, "none", False, True,
 "detail shot at water level of a man's open offered hands rising from dark moonlit water toward a woman's smaller hands, silver droplets, painterly water texture",
 "His hands rise open from the water and hers move toward them, droplets fall in slow painterly arcs, waves conceal the contact. Slow arc of the camera."),

("Доверие", "общий силуэт", "slow counter-orbit", 6.5, "none", False, True,
 "wide romantic moonlit ocean silhouette, a clearly adult man gently spinning a clearly adult woman once in chest-deep water like a knight holding a princess, both smiling, her shoulders above the surface, bodies fully concealed by dark water",
 "He turns with her in one slow controlled rotation, water splashes outward and catches the moonlight in painterly arcs. The camera makes a very slow partial orbit in the opposite direction. No fast spinning."),

("Доверие", "средний", "slow push-in", 5.5, "both", True, True,
 "moonlit medium two-shot, MARY sliding slowly down until she stands and wraps her arms around JOHN's neck, faces close, tender charged intimacy, water at chest level concealing their bodies",
 "She slides slowly downward and her arms come up around his neck, both breathing deeply, water moving around them. Slow push-in."),

("Финал", "крупный", "very slow push-in", 5.0, "both", True, True,
 "close moonlit two-shot, MARY and JOHN with foreheads almost touching in chest-deep dark water, his hands at her waist, overwhelming tenderness held one second before the kiss",
 "They drift the last few centimetres closer until foreheads almost touch, eyes closing slowly. Very slow push-in."),

("Финал", "силуэтный крупный", "slow partial orbit", 6.5, "both", True, True,
 "tasteful cinematic close shot of two clearly adult people sharing one tender kiss in the moonlit sea, heads, shoulders and upper backs visible, bodies fully concealed by dark water and shadow, silver moon rim light, deep teal mist, restrained emotion",
 "They move slowly into one tender kiss and remain still for a long beat. The camera performs a very slow partial orbit. Waves and reflected moonlight move naturally. No explicit contact."),

("Финал", "очень общий", "slow majestic pull-out", 8.0, "none", False, True,
 "very wide final composition, the night ocean under a huge silver moon, two tiny distant silhouettes close together in the water, vast starry sky, painterly waves, an open unfinished ending",
 "Slow majestic pull-out away from the two distant figures, waves roll, the moonlight path shimmers across the whole frame. Title card added in the edit, not generated."),
]


def build():
    shots = []
    for i, (section, size, camera, t, who, faces, tasteful, scene, motion) in enumerate(SHOTS):
        sid = "S01_SH%03d" % (i + 1)
        anchor = composition_anchor(size)

        looks = []
        if who in ("mary", "both"):
            looks.append(LOOK_MARY)
        if who in ("john", "both"):
            looks.append(LOOK_JOHN)

        identity = ""
        if faces:
            identity = ID_PAIR if who == "both" else ID_SINGLE

        if who == "both":
            scene = (scene + ", MARY stays on frame-left and JOHN stays on frame-right, "
                     "two clearly separated faces with visible space between them")

        # Порядок намеренно фиксирован: композиция -> сцена -> внешность ->
        # identity -> общий стиль -> персонажный стиль -> tasteful guard.
        parts = [anchor, scene] + looks
        if identity:
            parts.append(identity)
        parts.append(STYLE_BASE)
        if who != "none":
            parts.append(STYLE_CHARACTER)
        if tasteful:
            parts.append(TASTEFUL)
        parts.append(FRAME_GUARD)

        no_people = use_no_people_negative(who, tasteful, size)
        keyframe_negative = NEG_IMAGE
        if no_people:
            keyframe_negative += ", " + NEG_NO_PEOPLE

        shots.append({
            "shot_id": sid,
            "section": section,
            "duration_sec": round(float(t), 2),
            "frames_24fps": int(round(t * FPS)),
            "shot_size": size,
            "camera": camera,
            "seed": SEED_BASE + i * SEED_STEP,
            "who": who,
            "apply_face_id": faces,
            "face_order": (["mary", "john"] if who == "both" else ([who] if faces else [])),
            "face_targets": ({"mary": "left", "john": "right"} if who == "both"
                             else ({who: "largest"} if faces else {})),
            "non_explicit_water_scene": bool(tasteful),
            "no_people_negative_applied": no_people,
            "keyframe_prompt": ", ".join(parts),
            "keyframe_negative": keyframe_negative,
            "motion_prompt": motion + " " + ID_HOLD_VIDEO,
            "motion_negative": NEG_VIDEO,
        })

    total = sum(s["duration_sec"] for s in shots)

    pack = {
        "project": "Пляж",
        "version": 2,
        "style_target": "Arcane (Fortiche) painterly 3D animation",
        "route": "cloud free GPU (Colab/Kaggle) + ComfyUI",
        "target_runtime_sec": round(total, 1),
        "shot_count": len(shots),
        "master_specs": {"width": 1920, "height": 1080, "fps": FPS,
                         "loudness_lufs": -14.0, "true_peak_dbfs": -1.0},
        "content_policy": {
            "rating": "18+",
            "explicit_sexual_content": False,
            "identifiable_real_people_in_explicit_content": False,
            "note": "Интимные сцены — только неэксплицитно: силуэты, тёмная вода, тени."
        },
        "reference_photos": {
            "john": ["Пляж/Реальные фото/Джон/Епифанов И. С.-фото-1.png",
                     "Пляж/Реальные фото/Джон/IMG_5802.jpg"],
            "mary": ["Пляж/Реальные фото/Мэри/IMG_4805.jpg",
                     "Пляж/Реальные фото/Мэри/IMG_8409.jpg",
                     "Пляж/Реальные фото/Мэри/IMG_5025.jpg"]
        },
        "style_anchor_image": ("https://d8j0ntlcm91z4.cloudfront.net/"
                               "user_3GgYm9K5VTOcRs8lNMJHlvKh0iL/"
                               "hf_20260718_190542_6d8a5c8c-4312-4cdb-8969-b3e5b347842b.png"),
        "shared_blocks": {
            "style_base": STYLE_BASE, "style_character": STYLE_CHARACTER,
            "identity_single": ID_SINGLE, "identity_pair": ID_PAIR,
            "tasteful": TASTEFUL, "negative_image": NEG_IMAGE,
            "negative_no_people": NEG_NO_PEOPLE,
            "negative_video": NEG_VIDEO, "identity_hold_video": ID_HOLD_VIDEO,
        },
        "shots": shots,
    }

    os.makedirs(HERE, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(pack, f, ensure_ascii=False, indent=2)

    faces_n = sum(1 for s in shots if s["apply_face_id"])
    both_n = sum(1 for s in shots if s["who"] == "both")
    print("OK -> %s" % OUT)
    print("Планов: %d | хронометраж: %.1f c (%d:%02d)"
          % (len(shots), total, int(total // 60), int(total % 60)))
    print("С подстановкой лиц: %d (из них парных: %d)" % (faces_n, both_n))
    sections = {}
    for s in shots:
        sections[s["section"]] = sections.get(s["section"], 0) + s["duration_sec"]
    for k, v in sections.items():
        print("  %-14s %5.1f c" % (k, v))


if __name__ == "__main__":
    build()
