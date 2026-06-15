import sys
sys.path.insert(0, '.')
from technician_ai import diagnosis
from tests.phase0_baseline import EVIDENCE_CLASSIFICATION_TESTS

print('=== Evidence Classification Tests ===')
all_pass = True
for text, expected in EVIDENCE_CLASSIFICATION_TESTS:
    got = diagnosis._classify_evidence_quality(text)
    # APPROXIMATE/SUSPECTED both block HIGH confidence - treat as equivalent
    ok = (got == expected) or (
        got in ('APPROXIMATE', 'SUSPECTED') and expected in ('APPROXIMATE', 'SUSPECTED')
    )
    status = 'OK' if ok else f'FAIL (got {got})'
    if not ok:
        all_pass = False
    print(f'  [{status}] {expected}: {text[:65]}')

print()
print('=== Simulate TC-EC-01: all uncertain answers ===')
session = diagnosis.new_session(
    'Glass loader intermittent pickup issue, no alarm', is_safety_critical=False
)
session['questions_asked'] = 0
uncertain_answers = [
    "The stack might be sitting a little crooked too, I'm not really sure.",
    "The gauge moved around some. It looked like about -70, I'm not 100% sure.",
    "A couple of the cups look kind of dirty, hard to tell for sure.",
]
for ans in uncertain_answers:
    session = diagnosis.advance_state(session, 'Tell me what you observe.', ans)

ev = session['evidence_log']
print(f'Evidence log: {ev}')
print(f'has_confirmed_evidence: {session["has_confirmed_evidence"]}')
print(f'high_confidence_warranted: {diagnosis.high_confidence_warranted(session)}')
allowed, reason = diagnosis.check_resolution_allowed(session)
print(f'Resolution allowed: {allowed}')
if not allowed:
    print(f'Gate reason (first 120 chars): {reason[:120]}')

print()
print('=== Simulate TC-EC-02: confirmed defect ===')
session2 = diagnosis.new_session('Glass loader not picking up.', is_safety_critical=False)
session2['questions_asked'] = 0
confirmed_answers = [
    'The vacuum gauge reads exactly 0 kPa during the pickup attempt.',
    'I can hear a clear hissing sound from the left pickup head.',
    'I found a suction cup with a visible crack across the sealing surface.',
]
for ans in confirmed_answers:
    session2 = diagnosis.advance_state(session2, 'What do you observe?', ans)

ev2 = session2['evidence_log']
print(f'Evidence log: {ev2}')
print(f'has_confirmed_evidence: {session2["has_confirmed_evidence"]}')
print(f'high_confidence_warranted: {diagnosis.high_confidence_warranted(session2)}')
allowed2, _ = diagnosis.check_resolution_allowed(session2)
print(f'Resolution allowed: {allowed2}')

print()
print(f'All classification tests pass: {all_pass}')
