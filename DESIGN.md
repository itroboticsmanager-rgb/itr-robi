# ROBI Design System

## Direction

ROBI is a character-first reception kiosk for children and their parents. The
interface is soft, friendly and contemporary, but it must still read clearly
from a standing distance. The approved composition uses a permanent 3D school sign with occasional
ROBI appearances, one editorial banner and an always-visible 2x5 action
launcher.

The physical scene is a child and parent standing at a brightly lit school
reception, exploring for less than a minute while an administrator is busy.
That forces a light theme with strong text contrast and generous touch targets.

## Color strategy

The product surface is restrained: blue-tinted neutrals carry most of the UI,
ITRobotics blue marks the character and active actions, and warm yellow or coral
appears only for short emotional accents. Colors are authored conceptually in
OKLCH and stored as RGB tuples because pygame consumes RGB.

Semantic roles live in `app/src/robi/ui/theme.py`. Never use pure black or pure
white. A state must not depend on color alone.

## Typography

Use one local system family: Segoe UI Variable or Segoe UI, falling back to a
Unicode-capable sans. Use Regular for prose, Semibold for controls, and Bold
only for display headings. Keep headings to two lines and control labels to two
short words where possible.

## Spacing and shape

Use a 4 px base rhythm. Preferred steps are 8, 12, 16, 24, 32, 48, 64 and 96.
Corner radii are soft but not pill-shaped by default. Shadows are low-contrast
blue-gray and always paired with a subtle border so the UI remains legible on a
bright tablet display.

## Main composition

- School sign and editorial banner share remaining height in a 3:5 ratio.
- Action launcher uses content height, with 88 px rows (108 px on large displays).
- Actions use a left icon, clear label and trailing chevron. Neutral surfaces give all sections equal emphasis.
- Ten actions use 2x5; narrow screens use two columns with scrolling when needed.
- Eight items balance as 4+4; nine as 5+4; ten as 5+5.
- Icons always have text labels. Icon-only navigation is not permitted.
- More than ten actions use another page, never smaller targets.

## Motion

Touch feedback is 100-150 ms. Screen transitions are 180-260 ms. Character
reactions may run 500-1800 ms and must settle smoothly with quart or quint
ease-out timing. Avoid bounce, elastic motion, flashing and continuous ambient
movement. Expensive surfaces, type and scaled images are cached outside the
frame loop.

## Character

ROBI is rendered as a complete dimensional head, never as loose eyes on a flat
background. Its canonical near-square blue shell surrounds a light cyan face
panel, matching the supplied 3D references; large glossy eyes remain the
primary emotional channel and the small dark-blue brand smile adds secondary
expression. Compact placements preserve this exact silhouette and crop below
the face instead of stretching it. Idle behavior combines slow gaze settling, infrequent
blinks and tiny breathing motion. Every named mascot state must have a distinct
silhouette, gaze behavior, mouth shape or supporting mark, not merely a
different color.

## Accessibility and kiosk constraints

- Primary touch targets are at least 96 px on the 1920x1280 target.
- Body copy and labels maintain strong contrast on every surface.
- Gestures always have a visible affordance or a direct tap alternative.
- No essential animation uses flashing or abrupt full-screen motion.
- All content works offline from local data and the last valid banner cache.

## School sign, September 2026

The web kiosk always keeps the school logo in its top window. There is no
expanded mascot room, swipe-to-expand gesture or workshop API action. The
existing standalone character and workshop source modules remain available
for development, but the kiosk does not import them.

A saturated blue studio recess frames the yellow and porcelain-white 3D mark.
A broad light wash, a subtle lower rim and slowly changing bevel highlights
provide depth. The front remains readable; logo rotation stays within a few
degrees. This ambient brand scene is the deliberate exception to the product
UI rule against decorative motion.

ROBI appears for 11–15 seconds, followed by a 55–90 second pause. Eyes lead the
head, then the shoulders follow. Entrances and departures use quintic easing,
with zero endpoint velocity and acceleration. Waves have preparation, a slow
hand motion and a longer settle. No climbing, foot sliding or continuous dance.
A tap can greet while the character is settled; repeated taps cannot rewind
its departure or add two arm gestures together.

The visible canvas has its own buffer at the slot dimensions. Rendering follows
requestAnimationFrame and pauses while hidden or behind content. Reduced motion
keeps a static sign and stops frame scheduling. A local SVG is the fallback if
WebGL is unavailable. Physical Surface performance still requires device QA.


The logo front faces retain the original SVG colours without lighting washout.
Small lettering, wheel details and the emblem have only 1–1.8 SVG units of
relief, without a bevel; large letters have 10 units of depth and a 0.22-unit
bevel. The caption stays still while a short 12-second sequence moves individual
letter groups, passes a highlight and tilts the small robot icon. Wheel rotation
is continuous across sequence boundaries. Geometry is batched by material per
moving region. The canvas uses up to DPR 2 for crisp fine artwork.


The whole sign is now anchored at a fixed position and angle. Only internal
logo details animate. The stage uses an orthographic camera to avoid lateral
perspective distortion of ROBI in a wide strip. Cameos translate and rotate
one uniformly scaled rig. Six scenes have distinct staging: a two-step peek,
a greeting, inspecting the sign, leaning in from a side, and a shy peek followed
by a complete hide and a second appearance. A guide scene looks toward the actual banner or launcher position, then presents it with an open hand. The target receives a quiet temporary emphasis. Side exits clear the whole rig. Returning from content starts a fresh 55–90 second pause.


Launcher return restores the originating button and page, with a two-second tint.
Launcher buttons are the content root's items, which are the school's
pathways (the local example: «Робототехніка», «3D-моделювання»), so a parent
reaches a pathway in one tap. Decorative home captions are removed.

## Pathways and courses, September 2026

The CRM decides which pathways and levels the kiosk shows (Сайт → Кіоск ROBI);
texts, prices and covers are shared with the website. The tree is root →
pathway (menu) → course (card).

- A pathway button carries the pathway colour on its icon plate only; text
  stays ink-coloured, so no state depends on colour.
- A pathway page opens with its one-paragraph intro, then one row per course:
  cover (or the pathway icon), title, age and duration, price pill, chevron.
- A course page puts the cover (or a tinted pathway art panel) on the left and,
  on the right, age/duration chips, the description, up to four «Чого
  навчиться дитина» points and the price.
- Age is the first thing parents ask about, so it appears on the pathway
  button, on each course row and as the first chip of a course.
- A course without its own icon or colour inherits its pathway's.
- Single line breaks in authored text are joined; a blank line starts a
  paragraph.

Banner artwork delivery: 2400 × 800 px (3:1), PNG or WebP, including all desired
text. Keep essential copy 80 px from the artwork edges. Images occupy the full
banner surface with contain sizing, never cropping; surrounding space varies
with screen aspect and menu rows. The text/art split remains a fallback only.


## Banners

The kiosk has no built-in banners. It shows only banners the school publishes
to the kiosk in the CRM (`show_on_kiosk`). With none, the carousel is removed
entirely: the sign takes its height and the launcher stays at the bottom, and
Robi's guide scene points at the launcher only. A CRM banner without artwork
(or whose artwork fails to load) uses the text split with the local robotics
illustration.

Artwork fits within its panel at every height. Only the active slide animates;
12-second loops have resting phases, and slides advance after 14 seconds.
Pause stops both carousel advancement and artwork. Hidden pages, content screens,
reduced motion and mascot appearances suppress banner motion. An explicit
resume restarts autoplay even while its button retains keyboard focus.
