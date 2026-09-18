# Guide character (optional)

A mascot can make the assistant feel like a colleague rather than a form. It is optional; the assistant works without one. If you add one, make it serve the task — never compete with it.

## Contents

1. When to use one, and when not
2. Poses: a small, fixed vocabulary
3. Crops: one figure, many frames
4. Producing the art
5. Building the crops
6. The component
7. Where it appears
8. Tone

---

## 1. When to use one, and when not

Use one if the product already has a brand character, or the audience is non-technical and benefits from warmth. Skip it for dense professional tools where every pixel of the panel matters. Either way, the step text must stand on its own — the character's line is a supplement, never the only instruction.

## 2. Poses: a small, fixed vocabulary

Six poses cover everything. Each step names one; the definition picks what fits the moment:

| Pose | Use for |
|---|---|
| `welcome` | the launcher, empty states, first step of a task |
| `pointing` | "fill these in", the default for field steps |
| `explaining` | read-only and review steps, questions |
| `tablet` (or clipboard) | checking records, schedules, lists |
| `thumbs-up` | a quiet success; any success involving money, credit or a decline |
| `celebration` | a genuinely happy finish (published, sold) — sparingly |

Keep the list closed. A pose name that does not exist should fall back to `pointing`, not break the panel.

## 3. Crops: one figure, many frames

The panel shows the character at different sizes. Rather than one image scaled down (a tiny full-body figure is illegible), cut each pose into presets:

| Crop | Frame | Used in |
|---|---|---|
| `avatar` | a square around the head | collapsed pill, while typing, launcher rows |
| `closeup` | head and shoulders | small panel header |
| `chest` | down to mid-chest, keeps the hand gesture | the panel, default |
| `half` | to the waist | success screen |
| `full` | whole figure | onboarding, empty states |

Each crop keeps the gesture it exists to show — a crop of the pointing pose that cuts off the pointing hand is useless. So crop fractions are **tuned per pose**, measured from the figure's own alpha bounding box (not the canvas), and the avatar centres on the head, found from the alpha inside a "head band" near the top.

## 4. Producing the art

- One consistent character in all poses: same proportions, palette, line weight, lighting. Generate or draw all poses in one session from one reference sheet.
- Full body, facing three-quarters toward where the panel's text sits.
- Transparent PNG masters at ~2000px tall, generous margin. Keep the masters out of the public web root (e.g. `resources/guide/`).
- Check the character reads at 32px as an avatar. If it does not, simplify the design, not the crop.
- Make sure you have the rights to the art you ship.

## 5. Building the crops

`scripts/build-crops.py` (Python + Pillow) reads `<name>-<pose>.png` masters and writes WebP files `<name>-<pose>-<crop>.webp`, plus a JSON manifest of sizes. Edit its `CROPS` table per pose:

```python
CROPS = {
    #               closeup  chest   half    head band
    "welcome":     (0.40,   0.52,   0.66,   (0.02, 0.18)),
    "pointing":    (0.34,   0.46,   0.62,   (0.02, 0.18)),
    "celebration": (0.38,   0.54,   0.72,   (0.11, 0.28)),  # raised arms sit above the head
}
```

Fractions are of the figure's height from its top. Output widths are twice the largest display size (for high-DPI). Run it at build time, commit the WebP output (or build it in CI), and never ship the megabyte masters.

If the app wraps build scripts in its own CLI (e.g. an Artisan or npm script), wrap this one too, so a designer can drop in a new master and rebuild.

## 6. The component

```tsx
type Pose = 'welcome' | 'pointing' | 'explaining' | 'tablet' | 'thumbs-up' | 'celebration';
type Crop = 'avatar' | 'closeup' | 'chest' | 'half' | 'full';
const POSES: Pose[] = ['welcome', 'pointing', 'explaining', 'tablet', 'thumbs-up', 'celebration'];

export function Guide({ pose, crop = 'chest', className, priority = false }:
    { pose: string; crop?: Crop; className?: string; priority?: boolean }) {
    const safe = (POSES as string[]).includes(pose) ? pose : 'pointing';
    return (
        <img
            src={`/guide/guide-${safe}-${crop}.webp`}
            alt=""                      // decorative: the text beside it carries the meaning
            loading={priority ? 'eager' : 'lazy'}
            decoding="async"
            className={className}
            draggable={false}
        />
    );
}
```

`alt=""` is correct: the character's message is in the adjacent text. Give the element explicit width/height (from the manifest) to avoid layout shift.

## 7. Where it appears

- **Panel**: `chest` crop beside the step's one-line message; shrinks to `avatar` while an input has focus.
- **Collapsed pill**: `avatar`.
- **Launcher**: `welcome` in the header or empty state.
- **Success screen**: `half` in the step's success pose.
- **Resume card**: `avatar`.

Never animate it continuously. A single short entrance transition, disabled under `prefers-reduced-motion`, is plenty.

## 8. Tone

The character speaks in one short sentence per step, as an experienced colleague would: specific, calm, useful.

- Good: "Here is your schedule. The next payment due is the one you will send proof for."
- Bad: "Woohoo! Let's crush this payment together! 🎉"

No jokes on errors, no celebration around money, credit decisions, declines or anything the user might be anxious about. Give the character a name if the brand wants one — and keep it out of every message except the introduction.
