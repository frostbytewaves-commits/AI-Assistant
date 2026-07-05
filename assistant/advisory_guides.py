"""Curated deep-dive guides — factual build steps the LLM must not contradict."""

from __future__ import annotations

import re

from .advisory_topics import TOPICS

# game_id -> guide_key -> markdown body
GUIDES: dict[str, dict[str, str]] = {
    "minecraft": {
        "piglin": """## Zombified Piglin Farm (best AFK XP, vanilla)

**Idea:** Piglins spawn from Nether portals in the Overworld, turn into zombified piglins, then die in a kill chamber. You AFK with a Looting sword and collect XP orbs yourself.

### Materials
- Obsidian, flint & steel, building blocks, slabs, trapdoors
- Hoppers + chests (for gold/items only — **not** for XP)
- Water buckets, optional lava for kill chamber
- Looting III sword

### Layout
1. **Nether side:** Link a portal to an Overworld platform (classic gold farm geometry works).
2. **Overworld kill box:** Open trapdoors or half-slabs so piglins path into a central drop or blade chamber.
3. **Light** surrounding caves within 128 blocks so only portal spawns matter.
4. **Stand** where orbs reach you; use slabs so piglins cannot hit you.

### XP collection
- **You** walk into XP orbs after killing (or while AFK-killing). Hoppers and chests never collect XP.
- Furnaces only store XP from items **you** smelted through them — not from mob farms.

### Common mistakes
- Blocking portal spawning with wrong slab/trapdoor placement.
- Expecting hoppers to pick up XP (they only pick items).
- Forgetting to light nearby caves (cuts spawn rates).
""",
        "guardian": """## Guardian Farm (high XP burst)

**Idea:** Drain an ocean monument, create a spawning platform inside the structure, funnel guardians to a kill room, and kill them yourself for XP.

### Materials
- Sponges or sand/gravel for draining, building blocks, ladders/scaffolding
- Water streams, signs, magma blocks or solid kill method
- Hoe + Looting sword (optional), milk buckets for Mining Fatigue prep

### Layout
1. **Drain** the monument interior (or build a dry platform in the spawning zone).
2. **Platform** where guardians spawn (inside monument bounds).
3. **Water streams** push guardians into a central drop or kill chamber.
4. **Kill chamber:** player with sword — or magma/sweeping edge for automation (less XP unless you finish kills).

### XP collection
- Kill guardians **yourself** (or use a system that leaves last hit to you). Collect floating green orbs manually.
- Guardian drops (prismarine) → hoppers. XP orbs → player only.

### Common mistakes
- Building outside monument spawn rules (no guardians).
- Using full lava without item recovery plan.
- Confusing prismarine shards with XP — XP is always green orbs on the ground.
""",
        "spawner": """## Dungeon Spawner Grinder (zombie / skeleton XP)

**Idea:** Use a **monster spawner** found in a dungeon. Mobs spawn in a dark 9×9 room, get pushed into a drop shaft, you finish them at the bottom for XP.

### Materials
- Building blocks, water buckets, signs, hoppers + chest (loot only)
- Torches for **cave lighting** (see below)
- Optional: slab/half-block at kill spot

### Room rules
- Spawner active zone: **9×9 horizontal**, up to **4 blocks vertical** around the spawner.
- **Never place a torch ON the spawner block** — it stops spawning.
- **Do** light all other caves within ~128 blocks so the spawner is the main dark source.

### Classic layout
1. **9×9 room** with spawner centered; **2 blocks air** above spawner (3-high room for zombies/skeletons).
2. **Water streams** on the floor push mobs to one corner.
3. **Drop shaft** ~22 blocks: mobs land at half a heart; one hit with any weapon = player gets XP.
4. **Kill room** at bottom: stand on a slab, hit mobs, **walk through XP orbs**.

### Kill methods (trade-offs)
| Method | Pros | Cons |
|--------|------|------|
| Fall + manual hit | Full XP, simple | Needs exact height |
| Magma / campfire finish | Semi-AFK | Must ensure **you** get kill credit for XP |
| Lava blade | Fast | Burns drops; easy to lose XP if not designed carefully |

### What does NOT work
- **Furnaces/chests collecting XP** — false. Only the player (or certain kill-credit tricks) gets orbs.
- **Hoppers for XP** — they only move items.
- **Soul torches on the spawner** — stops spawning (bad for farms).
- **Soul sand "drowning pit"** alone — soul sand makes bubble columns, not a drowning trap by itself.

### Common mistakes
- Lighting the spawner block itself.
- Drop too short (mobs survive) or too long (mobs die with no player kill → no XP).
- Leaving nearby caves dark (slow spawn rates).
""",
        "enderman": """## Enderman Farm (late-game massive XP)

**Idea:** Build high in the End dimension on an enderman-only platform. Endermen spawn in large numbers, fall or funnel into a kill area; you AFK-kill for huge XP.

### Materials
- End stone / building blocks, water, trapdoors, minecart + hopper (items only)
- Ender pearls for travel, blocks to bridge away from main island
- Looting III sword

### Layout (simplified)
1. **Bridge** ~128 blocks from the main End island to reduce other mob spawns.
2. **Platform** ~41 blocks above a kill pit (classic design uses endermen teleport behavior + aggro).
3. **Name tag** a pig or use trapdoors so endermen aggro and fall.
4. **Kill floor:** stand where you can hit feet of endermen; collect XP orbs yourself.

### XP collection
- Player kills with sword (Looting for pearls). Hoppers optional for pearl pickup only.

### Common mistakes
- Building on main island without clearing spawn space.
- Expecting automatic XP storage in blocks/containers.
""",
    },
}

MINECRAFT_XP_GUIDE_KEYS = ("piglin", "guardian", "spawner", "enderman")

TITLE_ALIASES: dict[str, tuple[str, str]] = {
    "piglin": ("minecraft", "piglin"),
    "zombified": ("minecraft", "piglin"),
    "guardian": ("minecraft", "guardian"),
    "monument": ("minecraft", "guardian"),
    "blaze": ("minecraft", "spawner"),
    "mob grinder": ("minecraft", "spawner"),
    "spawner": ("minecraft", "spawner"),
    "dungeon": ("minecraft", "spawner"),
    "zombie": ("minecraft", "spawner"),
    "skeleton": ("minecraft", "spawner"),
    "xp orb": ("minecraft", "spawner"),
    "enemy farm": ("minecraft", "spawner"),
    "enderman": ("minecraft", "enderman"),
}


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title.lower().strip())


def lookup_guide_by_key(game_id: str, key: str) -> str | None:
    return GUIDES.get(game_id, {}).get(key)


def resolve_guide(game_id: str | None, option_title: str) -> str | None:
    """Match a selected option title to a curated guide."""
    if not game_id or not option_title.strip():
        return None
    title = _normalize_title(option_title)
    for fragment, (gid, key) in TITLE_ALIASES.items():
        if gid == game_id and fragment in title:
            guide = lookup_guide_by_key(gid, key)
            if guide:
                return guide
    for spec in TOPICS:
        if spec["game"] != game_id:
            continue
        for idx, (opt_id, opt_title, _teaser) in enumerate(spec["options"]):
            norm = _normalize_title(opt_title)
            if norm == title or title in norm or norm in title:
                if spec["id"] == "minecraft_xp" and idx < len(MINECRAFT_XP_GUIDE_KEYS):
                    return lookup_guide_by_key(game_id, MINECRAFT_XP_GUIDE_KEYS[idx])
    return None
