# Build and install the Steam Frame version

These steps build a standalone Linux ARM64 game for the Frame. A Mac isn't required. The Windows desktop build described by upstream is a different target; use the Docker route below for standalone Frame play.

## Choose a build machine

| Machine | What to use |
| --- | --- |
| Frame Desktop / ARM64 Linux | Docker Engine, running ARM64 containers natively |
| Windows x86_64 | WSL2 Ubuntu and Docker Desktop with Linux containers and WSL integration |
| macOS | Docker Desktop, or another Docker environment that can run `linux/arm64` |
| Linux x86_64 | Docker Engine with ARM64 container emulation |

The wrapper always requests `--platform linux/arm64`. Apple Silicon and ARM64 Linux build natively; x86_64 hosts run the compiler through emulation. The previously recorded complete build used ARM64 Docker. The x86_64 routes use the same image and scripts, but haven't had a fresh full-game build here.

You need Bash, Git, Python 3 and `shasum` on the machine running the wrapper. All game compilers and libraries are installed inside the image. You also need a running Docker engine and enough space for the image, dependencies and build outputs.

- **Windows:** [install WSL2 Ubuntu](https://learn.microsoft.com/en-us/windows/wsl/install), then [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/). Enable Docker's integration for that Ubuntu distribution. Run the commands below in **Ubuntu**, with the checkout under `~/src`, rather than PowerShell or `/mnt/c`. Inside Ubuntu, `sudo apt-get update` and `sudo apt-get install git python3 perl rsync openssh-client` supply the host utilities. A Windows ROM path such as `C:\Users\you\Games\mk64.us.z64` becomes `/mnt/c/Users/you/Games/mk64.us.z64` in WSL.
- **macOS:** install Git and Python 3, then start Docker Desktop. `shasum` is supplied by the system Perl installation. Colima also works if its VM is ARM64 or has ARM64 emulation.
- **Linux:** install Docker Engine using your distribution's instructions. On Ubuntu, install `git python3 perl rsync openssh-client` for the wrapper. Docker Desktop includes ARM64 emulation; standalone x86_64 Docker Engine needs [the emulation setup described by Docker](https://docs.docker.com/build/building/multi-platform/#qemu).
- **Frame Desktop:** run these commands in a Desktop terminal once Docker Engine and the host utilities are available. If Docker isn't set up on your Frame, use a computer route above. Building on the Frame doesn't require a second computer or copying the resulting game over SSH.

Check the engine before starting:

```sh
docker version
docker run --rm --platform linux/arm64 ubuntu:22.04 uname -m
```

The second command should print `aarch64`. An `exec format error` means the Docker environment cannot run ARM64 containers yet.

## Build

Use your own supported **US Mario Kart 64 ROM in `.z64` format**. The script checks its identity and rejects other revisions. Keep optional Amped Up files separate; [AMPED_UP.md](docs/AMPED_UP.md) covers its data requirements.

```sh
mkdir -p "$HOME/src"
cd "$HOME/src"
git clone --recurse-submodules --branch main https://github.com/astromaddie/mariokart64-vr.git
cd mariokart64-vr
export MK64_ROM="/path/to/your/mk64.us.z64"
MK64_VR=ON JOBS=4 bash tools/docker/build-linux.sh all
```

Use a path visible to your chosen shell, and keep the quotes if it contains spaces. `MK64_VR=ON` is required for the VR build; the script's default is flat mode. Reduce `JOBS` if memory is tight.

`all` creates the pinned Ubuntu 22.04 ARM64 image, builds the recompilers, generates game code from your ROM, builds the VR game, stages its files, checks the Linux ABI and runs a container startup check. The generated code and staged ROM are local build inputs and stay outside Git.

The ready-to-copy folder is:

```text
build-linux-aarch64/package/MarioKart64Recompiled/
```

Copy the **whole folder**, including `lib/`, `assets/`, `APP-DATA-NAME` and `LAUNCH-STEAM-FRAME.sh`. The package excludes the ROM, saves and Vulkan drivers. `BUILD-METADATA.json` records the source and build inputs. The container startup check is a build check; it doesn't measure Frame gameplay performance.

## Install on Frame Desktop

Close the game before replacing its files. From the checkout on the Frame:

```sh
mkdir -p "$HOME/Games/MarioKart64VR" "$HOME/.local/share/MK64FrameVR"
cp -a build-linux-aarch64/package/MarioKart64Recompiled/. "$HOME/Games/MarioKart64VR/"
cp "$MK64_ROM" "$HOME/.local/share/MK64FrameVR/mk64.us.z64"
chmod +x "$HOME/Games/MarioKart64VR/LAUNCH-STEAM-FRAME.sh"
```

In Desktop Steam, choose **Games → Add a Non-Steam Game**, browse to `~/Games/MarioKart64VR/LAUNCH-STEAM-FRAME.sh`, and add it. Set its name to `MarioKart64VR`, its **Start In** folder to `~/Games/MarioKart64VR`, and its launch options to `--game mk64`. Use the full `/home/steamos/...` paths in Steam's fields. It is a native ARM64 Linux game; use an ARM64 Steam Linux Runtime if selecting a compatibility runtime, rather than Proton.

Return to the headset's Steam library and launch that entry. Starting the executable directly from a terminal bypasses SteamVR's controller setup.

## Install from another computer

[Valve's SteamOS Devkit Client guide](https://partner.steamgames.com/doc/steamhardware/steamframe/loadgames) covers pairing and uploading. Enable Developer Mode on the Frame, pair your computer, then use **Title Upload**:

| Field | Value |
| --- | --- |
| Name | `MarioKart64VR` |
| Local Folder | The full `build-linux-aarch64/package/MarioKart64Recompiled` folder |
| Start Command | `./LAUNCH-STEAM-FRAME.sh --game mk64` |
| Runtime | Steam Linux Runtime 3.0 ARM64 (Sniper) |

On Windows, the built folder is accessible in Explorer through `\\wsl.localhost\Ubuntu\home\YOUR_WSL_USER\src\mariokart64-vr\build-linux-aarch64\package\MarioKart64Recompiled`. Adjust the distribution and username to yours.

Keep the ROM outside the uploaded package. Copy it to `~/.local/share/MK64FrameVR/mk64.us.z64` on the Frame with its Desktop file manager or, from your macOS/Linux/WSL terminal after SSH pairing:

```sh
export FRAME_HOST="steamos@YOUR_FRAME_ADDRESS"
ssh "$FRAME_HOST" 'mkdir -p "$HOME/.local/share/MK64FrameVR"'
scp "$MK64_ROM" "$FRAME_HOST:.local/share/MK64FrameVR/mk64.us.z64"
```

The upload creates a Steam library entry. Launch it there for controllers and VR. Reuse the same title name for updates, with the game closed. Saves, settings, ROM and mods stay in `~/.local/share/MK64FrameVR`, outside the installed application folder.

## ROM-free checks and upstream desktop builds

The [README](README.md#rom-free-vr-checks) describes the public VR checks; those don't build the game or need a ROM. For Windows/Linux desktop development, start with the [upstream project](https://gitlab.com/sonicdcer/MarioKart64Recomp). Its desktop executable is separate from this Docker-built Frame package.
