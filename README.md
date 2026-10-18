# Catherine: Full Body Vita3K patch

A [Vita3K](https://github.com/Vita3K/Vita3K) game patch for Catherine: Full Body (PCSG01179). It fixes the game freezing:
- on the "Stage 3 Torture Chamber" card at the start of night 3;
- when Stage 6 (Clock Tower) loads.

In both cases Vita3K's log fills with `Invalid read of uint32_t at address: 0x4c` ([Vita3K#3002](https://github.com/Vita3K/Vita3K/issues/3002)). The patch only changes game code, so it works with the regular Vita3K builds. You don't need a custom Vita3K build.

## Which file to use

There is one file per game version. The code offsets differ between versions, so the wrong file breaks the game. Use exactly one:

| Your game | File |
|---|---|
| 1.03 update, including the English patch (it's built on 1.03) | [`v1.03/PCSG01179_fogfix_v103.txt`](v1.03/PCSG01179_fogfix_v103.txt) |
| 1.00, no update | [`v1.00/PCSG01179_fogfix_v100.txt`](v1.00/PCSG01179_fogfix_v100.txt) |

The game list on Windows shows the version. Vita3K also logs it when the game starts: `Version: 1.03`.

## Install

Copy the file into Vita3K's `patch` folder. Keep the file name as it is. Vita3K loads every file there whose name contains `PCSG01179` and ends in `.txt`, so don't put both versions' files in the folder.

- Windows: the `patch` folder next to `Vita3K.exe`, or `portable\patch` if you use a portable folder.
- Android: `Android/data/org.vita3k.emulator/files/patch/` on internal storage. Changing the emulator storage folder in the settings doesn't move it. Some file managers can't open `Android/data`. Copying the file from a PC over USB is one way around that.

Vita3K reads patches when the game starts. A working install logs `Found 2 patches for titleid PCSG01179`. If the log says 4, both files are in the folder.

## What it does

The game has no shader compiler at runtime. Two caches, filled from the precompiled shaders in `Shader.cpk`, give each material its shaders and its vertex+fragment program pair. A key that isn't in the cache gets a NULL program. On hardware that never happens, but the game would crash if it did.

When the night 3 Nightmare stage loads, a job thread builds the stage model's material keys. On hardware, the stage environment has already turned fog off by then. On Vita3K the job gets there sooner, while fog is still on. It asks for fog variants of the shaders that aren't in the caches. Then the game keeps reading through the NULL program, which is the `0x4c` spam, and never gets past the loading card. The Stage 6 load misses the same way.

For both caches, the patch changes only what happens on a miss:
1. Look the key up again with the fog bits cleared. These are the shaders the stage uses on hardware.
2. If that also misses, run the original miss code.

Lookups that hit run unchanged. The comments at the top of each file show the original and patched instructions.

## Tested

Windows 11, AMD Radeon RX 9070 XT, Vulkan:
- English (1.03 + English patch), Safety difficulty: played from night 3 through Stage 6, clearing Stages 3, 4, 5 (with the boss) and 6 (all floors and the boss). Neither freeze happened. The fallback ran when night 3 and Stage 6 loaded.
- Japanese 1.00 and Japanese 1.03: night 3 loads, and Stage 3 floor 1 plays through to the results screen.

Not tested yet:
- Android. The patch doesn't depend on the GPU, but it hasn't been run there.
- Stage 7 and later.
- The 1.00 file past Stage 3.

## Not fixed by this patch

- With the AMD Windows graphics driver, Vita3K crashes on Stage 5 floor 2. The crash is in the driver's shader compiler, so it needs a Vita3K-side workaround, not a game patch. The bug is specific to AMD's Windows driver.
- Some labels in the phone's save menu render as solid white boxes.

## Rebuilding the patch

`tools/fog_fallback.py` builds the patch lines for an eboot. It needs Python with `capstone` and `keystone-engine`.

```
python tools/fog_fallback.py text.bin
```

`text.bin` is the game's code segment (segment 0, loaded at `0x81000000`), taken from a decrypted eboot. The script finds both cache functions by their byte patterns and reads the call targets from the original code. It stops with an error if the code isn't what it expects. It prints the instruction listing and the `[eboot.bin]` patch lines. The description at the top of each file is written by hand.
