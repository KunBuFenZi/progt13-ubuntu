#!/usr/bin/env python3
"""Backport stable GNOME 50 OSK fixes and preserve captured touch sequences."""
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[2]
original=(root/'reference/gnome50/keyboard-original.js').read_text(encoding='utf-8')
assert hashlib.sha256(original.encode()).hexdigest()=='847c837f35874d12b1bda312b1209c72f3aad7d58ee5705dc38af8bf14c9c67a'
source=original

def replace(old,new):
    global source
    assert source.count(old)==1,old[:140]
    source=source.replace(old,new)

# Stable gnome-50 commits ac2fb580 and 61b16d41, without the unrelated
# popup animation API change in the later branch.
replace('const modifierKeys = this._modifierKeys[key.keyval] || [];',
        'const modifierKeys = this._modifierKeys.get(key.keyval) ?? [];')
replace('this._modifierKeys[key.keyval] = modifierKeys;',
        'this._modifierKeys.set(key.keyval, modifierKeys);')
replace('for (const key of this._modifierKeys[keyval])',
        'for (const key of this._modifierKeys.get(keyval))')
replace('''        keyboardModel.getLevels().forEach(currentLevel => {''',
        '''        this._modifiers.clear();
        this._modifierKeys.clear();

        keyboardModel.getLevels().forEach(currentLevel => {''')

# Count delivery without retaining key values or the text being entered.
replace("        this.emit('pressed');\n        this._pressed = true;",
        "        tbTouchCount('keyPressed');\n        this.emit('pressed');\n        this._pressed = true;")
replace("        if (this._pressed) {\n            if (this._keyval",
        "        if (this._pressed) {\n            tbTouchCount('keyReleased');\n            if (this._keyval")

helper=(root/'port/gnome/touch-dispatch-compat.js').read_text(encoding='utf-8')
helper+='\n'+(root/'port/gnome/touch-live-diagnostics.js').read_text(encoding='utf-8')
replace('export const KEYBOARD_ANIMATION_TIME = 150;',helper+'\nexport const KEYBOARD_ANIMATION_TIME = 150;')
replace('''        this._keyboard = null;
        this._a11yApplicationsSettings''',
        '''        this._keyboard = null;
        tbObserveStage();
        this._a11yApplicationsSettings''')
old='''    maybeHandleEvent(event) {
        if (!this._keyboard)
            return false;

        const actor = global.stage.get_event_actor(event);

        if (Main.layoutManager.keyboardBox.contains(actor) ||
            !!actor._extendedKeys || !!actor.extendedKey) {
            actor.event(event, true);
            actor.event(event, false);
            return true;
        }

        return false;
    }'''
new='''    maybeHandleEvent(event) {
        if (!this._keyboard)
            return false;

        const type = event.type();
        const sequence = event.get_event_sequence();
        const begin = type === Clutter.EventType.TOUCH_BEGIN;
        const end = type === Clutter.EventType.TOUCH_END;
        const cancel = type === Clutter.EventType.TOUCH_CANCEL;
        const slot = sequence?.get_slot();
        const options = tbTouchOptions();
        if (this._tbKeyboard !== this._keyboard || !options.pickFallback) {
            this._tbTouchActors = new Map();
            this._tbKeyboard = this._keyboard;
        }
        let actor = global.stage.get_event_actor(event);
        if (sequence)
            tbTouchCount(`event_${type}`);
        if (!actor)
            tbTouchCount(`missing_${type}`);

        // A new contact must never inherit a stale target from a reused slot.
        if (begin)
            this._tbTouchActors.delete(slot);
        if (!actor && sequence && options.pickFallback) {
            const previous = this._tbTouchActors.get(slot);
            if (previous?.get_stage() && !tbPopupForActor(previous)) {
                actor = previous;
                tbTouchCount('sequenceTarget');
            } else {
                const [x, y] = event.get_coords();
                actor = global.stage.get_actor_at_pos(Clutter.PickMode.REACTIVE, x, y);
                tbTouchCount('pickedTarget');
            }
        }

        const isKeyboard = tbKeyboardTarget(actor);
        if (begin && isKeyboard && options.pickFallback)
            this._tbTouchActors.set(slot, actor);
        if (end || cancel)
            this._tbTouchActors.delete(slot);
        if (!isKeyboard) {
            if (sequence)
                tbTouchCount(`outside_${type}`);
            return false;
        }
        if (cancel) {
            tbCancelKeyboardActor(actor);
            tbTouchCount('cancelled');
            return true;
        }
        actor.event(event, true);
        actor.event(event, false);
        if (sequence)
            tbTouchCount(`forwarded_${type}`);
        return true;
    }'''
replace(old,new)
replace('''        if (targetActor === this.actor ||
            this.actor.contains(targetActor))''',
        '''        if (targetActor && (targetActor === this.actor ||
            this.actor.contains(targetActor)))''')
replace('''        if (targetActor === this._boxPointer.bin ||
            this._boxPointer.bin.contains(targetActor))''',
        '''        if (targetActor && (targetActor === this._boxPointer.bin ||
            this._boxPointer.bin.contains(targetActor)))''')
out=root/'port/gnome/keyboard.js'
out.write_bytes(source.encode('utf-8'))
proof={'source':'Device GNOME 50.1 keyboard resource',
       'original_sha256':hashlib.sha256(original.encode()).hexdigest(),
       'patched_sha256':hashlib.sha256(source.encode()).hexdigest(),
       'stable_backports':['ac2fb580fee9adf966d2ba3195e7cf067ac2eada','61b16d4124d2d15e5bf98f5bcebbecedf9d28c96'],
       'compatibility':'Mutter18 lacks the newer input-panel-group API; preserve and pick keyboard targets during the lock-screen grab',
       'diagnostics':'Event counters and generated Shift target geometry; no entered text or real finger coordinates',
       'status':'PREPARED_NOT_RUNTIME_TESTED'}
(root/'port/gnome/touchguard-source.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
print(json.dumps(proof,indent=2))
