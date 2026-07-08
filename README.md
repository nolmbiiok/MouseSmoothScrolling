# MouseSmoothWheel

A lightweight Windows utility that adds smooth inertia scrolling to any mouse.

MouseSmoothWheel makes normal mouse wheel scrolling feel smoother by adding a short inertia effect after each wheel input.

## Features

- Smooth inertia scrolling for mouse wheel input
- Tray icon support
- Low / Normal / Strong scroll presets
- Quick exit from the tray menu
- Works with most standard Windows applications

## Usage

- Right-click the tray icon to change scroll strength or exit
- Double-click the tray icon to cycle between presets

## Behavior

When the mouse wheel is scrolled quickly 4 or more times, MouseSmoothWheel switches to smooth inertia scrolling.

Small wheel inputs remain close to normal Windows mouse wheel behavior.

## Download

Download the latest `MouseSmoothWheel-v*.exe` file from the [Releases](../../releases) page.

For example:

```text
MouseSmoothWheel-v0.1.0.exe


## Known issues

- Remaining inertia input may continue even after the mouse cursor moves to another window.
- Smooth scrolling may not feel perfectly smooth in some applications.
