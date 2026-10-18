// Bounded RAM-only diagnostics. Configuration is root-owned under /run.
// No password text or real finger coordinates are read or written.
const tbDiagRoot = `${GLib.get_user_runtime_dir()}/tb378fc-touch`;
let tbDiagSnapshotId = '';
let tbDiagWakeId = '';
let tbDiagProbeId = '';
let tbDiagProbe = null;
let tbDiagKeyboard = null;
let tbDiagTouch = null;

function tbDiagWrite(name, value) {
    GLib.mkdir_with_parents(tbDiagRoot, 0o700);
    const bytes = new TextEncoder().encode(`${JSON.stringify(value, null, 2)}\n`);
    Gio.File.new_for_path(`${tbDiagRoot}/${name}.json`).replace_contents(
        bytes, null, false,
        Gio.FileCreateFlags.PRIVATE | Gio.FileCreateFlags.REPLACE_DESTINATION,
        null);
}

function tbDiagActor(actor) {
    if (!actor)
        return null;
    const [x, y] = actor.get_transformed_position();
    const [width, height] = actor.get_transformed_size();
    return {mapped: actor.is_mapped(), visible: actor.visible,
        reactive: actor.reactive, opacity: actor.get_paint_opacity(),
        x, y, width, height};
}

function tbDiagShiftButton() {
    const keyboard = Main.keyboard?.keyboardActor;
    for (const layer of Object.values(keyboard?._layers ?? {})) {
        for (const key of layer.shiftKeys ?? []) {
            if (key.keyButton.is_mapped() && key.keyButton.get_paint_opacity() > 0)
                return key.keyButton;
        }
    }
    return null;
}

function tbDiagSnapshot() {
    const shield = Main.screenShield;
    const dialog = shield?._dialog;
    return {monotonicMs: Math.round(GLib.get_monotonic_time() / 1000),
        locked: shield?.locked ?? false, shieldActive: shield?.active ?? false,
        actionMode: Main.actionMode,
        keyboard: tbDiagActor(Main.keyboard?.keyboardActor),
        keyboardBox: tbDiagActor(Main.layoutManager.keyboardBox),
        shiftTarget: tbDiagActor(tbDiagShiftButton()),
        prompt: tbDiagActor(dialog?._authPrompt),
        shortLightbox: tbDiagActor(shield?._shortLightbox),
        longLightbox: tbDiagActor(shield?._longLightbox),
        idleMs: global.backend.get_core_idle_monitor().get_idletime(),
        totals: {...tbTouchTotals}};
}

function tbDiagWake() {
    const seat = global.stage.context.get_backend().get_default_seat();
    tbDiagKeyboard ??= seat.create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
    tbDiagKeyboard.notify_keyval(GLib.get_monotonic_time(), Clutter.KEY_Control_L,
        Clutter.KeyState.PRESSED);
    tbDiagKeyboard.notify_keyval(GLib.get_monotonic_time(), Clutter.KEY_Control_L,
        Clutter.KeyState.RELEASED);
}

function tbDiagStopProbe(error = null) {
    const probe = tbDiagProbe;
    if (!probe)
        return;
    if (probe.down) {
        tbDiagTouch.notify_touch_up(GLib.get_monotonic_time(), 0);
        probe.down = false;
    }
    probe.error = error;
    probe.status = error ? 'ABORTED' : 'CONTACTS_SENT_PENDING_DELIVERY_COUNTS';
    GLib.timeout_add(GLib.PRIORITY_DEFAULT, 600, () => {
        probe.after = tbDiagSnapshot();
        tbDiagWrite('probe', probe);
        tbDiagProbe = null;
        return GLib.SOURCE_REMOVE;
    });
}

function tbDiagStartProbe(id) {
    if (tbDiagProbe)
        return;
    const before = tbDiagSnapshot();
    if (!before.locked || !before.shiftTarget?.mapped || !before.keyboard?.mapped) {
        tbDiagWrite('probe', {id, status: 'NOT_STARTED',
            reason: 'The locked screen must have a mapped keyboard and Shift key', before});
        return;
    }
    const seat = global.stage.context.get_backend().get_default_seat();
    tbDiagTouch ??= seat.create_virtual_device(Clutter.InputDeviceType.TOUCHSCREEN_DEVICE);
    tbDiagProbe = {id, before, contacts: 0, down: false, status: 'RUNNING',
        scope: 'Compositor virtual touch to the current Shift actor; excludes hardware and libinput'};
    tbDiagWrite('probe', tbDiagProbe);
    function step() {
        if (!tbDiagProbe)
            return GLib.SOURCE_REMOVE;
        try {
            if (!Main.screenShield.locked)
                throw new Error('The screen is no longer locked');
            const actor = tbDiagShiftButton();
            if (!actor || !Main.keyboard.keyboardActor?.is_mapped())
                throw new Error('The keyboard target is no longer mapped');
            const {x, y, width, height} = tbDiagActor(actor);
            tbDiagTouch.notify_touch_down(GLib.get_monotonic_time(), 0,
                x + width / 2, y + height / 2);
            tbDiagProbe.down = true;
            GLib.timeout_add(GLib.PRIORITY_DEFAULT, 80, () => {
                if (!tbDiagProbe)
                    return GLib.SOURCE_REMOVE;
                try {
                    tbDiagTouch.notify_touch_up(GLib.get_monotonic_time(), 0);
                    tbDiagProbe.down = false;
                    tbDiagProbe.contacts++;
                    if (tbDiagProbe.contacts >= 20)
                        tbDiagStopProbe();
                    else
                        GLib.timeout_add(GLib.PRIORITY_DEFAULT, 120, step);
                } catch (e) {
                    tbDiagStopProbe(e.message);
                }
                return GLib.SOURCE_REMOVE;
            });
        } catch (e) {
            tbDiagStopProbe(e.message);
        }
        return GLib.SOURCE_REMOVE;
    }
    GLib.timeout_add(GLib.PRIORITY_DEFAULT, 300, step);
}

function tbDiagPoll(options) {
    try {
        const snapshotId = String(options.snapshotId ?? '');
        if (snapshotId && snapshotId !== tbDiagSnapshotId) {
            tbDiagSnapshotId = snapshotId;
            tbDiagWrite('state', {id: snapshotId, ...tbDiagSnapshot()});
        }
        const wakeId = String(options.wakeId ?? '');
        if (wakeId && wakeId !== tbDiagWakeId) {
            tbDiagWakeId = wakeId;
            tbDiagWake();
        }
        const probeId = String(options.probeId ?? '');
        if (probeId && probeId !== tbDiagProbeId && !tbDiagProbe) {
            tbDiagProbeId = probeId;
            tbDiagStartProbe(probeId);
        }
    } catch (e) {
        tbDiagWrite('error', {error: e.message});
    }
}
