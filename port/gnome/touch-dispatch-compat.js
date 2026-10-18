// GNOME 50 compatibility for OSK events captured by the lock-screen grab.
// No key values, text, coordinates, or actor labels enter diagnostics.
const tbTouchFile = Gio.File.new_for_path('/run/tb378fc-touch-dispatch.json');
let tbTouchConfig = {pickFallback: true, trace: true};
let tbTouchLastConfig = 0;
let tbTouchCounts = {};
let tbTouchTotals = {};
let tbTouchReport = 0;
let tbStageSignal = 0;

function tbObserveStage() {
    if (tbStageSignal)
        return;
    // Modal grabs start propagation at uiGroup, skipping the stage ancestor.
    tbStageSignal = Main.uiGroup.connect('captured-event', (_group, event) => {
        const type = event.type();
        if (type >= Clutter.EventType.TOUCH_BEGIN &&
            type <= Clutter.EventType.TOUCH_CANCEL) {
            tbTouchCount(`stage_${type}`);
            const age = GLib.get_monotonic_time() / 1000 - event.get_time();
            if (age >= 0 && age < 60000 && tbTouchOptions().trace)
                tbTouchCounts.stageMaxAgeMs = Math.max(
                    tbTouchCounts.stageMaxAgeMs ?? 0, Math.round(age));
        }
        return Clutter.EVENT_PROPAGATE;
    });
    let previous = GLib.get_monotonic_time();
    GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1000, () => {
        const now = GLib.get_monotonic_time();
        const late = Math.round((now - previous) / 1000) - 1000;
        previous = now;
        tbDiagPoll(tbTouchOptions());
        if (late > 100 && tbTouchOptions().trace) {
            tbTouchCounts.mainLoopMaxLateMs = Math.max(
                tbTouchCounts.mainLoopMaxLateMs ?? 0, late);
            tbTouchCount('mainLoopLate');
        }
        return GLib.SOURCE_CONTINUE;
    });
}

function tbTouchOptions() {
    const now = GLib.get_monotonic_time();
    if (now - tbTouchLastConfig > 500000) {
        tbTouchLastConfig = now;
        try {
            const [, bytes] = tbTouchFile.load_contents(null);
            const options = JSON.parse(new TextDecoder().decode(bytes));
            tbTouchConfig = {
                pickFallback: options.pickFallback === true,
                trace: options.trace === true,
                snapshotId: options.snapshotId,
                wakeId: options.wakeId,
                probeId: options.probeId,
            };
        } catch {
            // The built-in defaults work before the optional RAM file exists.
        }
    }
    return tbTouchConfig;
}

function tbTouchCount(name) {
    tbTouchTotals[name] = (tbTouchTotals[name] ?? 0) + 1;
    if (!tbTouchOptions().trace)
        return;
    tbTouchCounts[name] = (tbTouchCounts[name] ?? 0) + 1;
    if (tbTouchReport)
        return;
    tbTouchReport = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 3, () => {
        console.warn(`TB378FC_OSK_DISPATCH ${JSON.stringify(tbTouchCounts)}`);
        tbTouchCounts = {};
        tbTouchReport = 0;
        return GLib.SOURCE_REMOVE;
    });
}

function tbKeyboardTarget(actor) {
    return actor && (Main.layoutManager.keyboardBox.contains(actor) ||
        !!actor._extendedKeys || !!actor.extendedKey);
}

function tbPopupForActor(actor) {
    for (let node = actor, i = 0; node && i < 6; node = node.get_parent(), i++) {
        if (node._boxPointer?.visible)
            return true;
    }
    return false;
}

function tbCancelKeyboardActor(actor) {
    for (let node = actor, i = 0; node && i < 6; node = node.get_parent(), i++) {
        if (typeof node.cancel === 'function' && node.keyButton) {
            node.cancel();
            node._pressed = false;
            node.keyButton.remove_style_pseudo_class('active');
            return;
        }
    }
}
