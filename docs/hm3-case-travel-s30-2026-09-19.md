# Travel case for the provenance figure: travel-s30-test-000 (test seed 30)

Selection rule (preregistered): the first incident on test seed 30 in the provenance run's own order. Graph artifact SHA `e1b6c6be977ee0e2` is the one used for forward selection and backward trace.

## 1. The intervention and the correct repair

Query: Flight F14 (Chen, day 1) now arrives at 23:30.

Intervention: `{"op": "shift_reservation", "object_id": "F14", "payload": {"arrival": 1410}}`

Oracle repair transactions (A):
- shift_reservation(S93, rev=1, {"checkin": 1470, "late_arrival": 1})

Hidden policy keys the oracle consulted: buffer[P51], auto_rebook[P51], enforce_late[H82]; required witness records: h24, h25, h5, h7.

## 2. The history (write / hold / read events as outcome records)

Kind `intervention` = an earlier change; `auto` = the environment followed automatically; `txn` = a manual repair. Records in time order; **bold** = required witnesses; the corrupted record is marked.

| rid | seg | kind | op | object | delta / payload |
|---|---|---|---|---|---|
| h0 | 0 | intervention | shift_reservation | F51 | arrival:825→1200 |
| h1 | 0 | txn | shift_reservation | T27 | pickup:840→1225 |
| h2 | 0 | txn | shift_reservation | S70 | checkin:890→1275 |
| h3 | 0 | txn | cancel_reservation | D84 | status:active→cancelled |
| h4 | 0 | txn | rebook_bundle | B52 | rebooked:0→1 |
| **h5** | 1 | intervention | shift_reservation | F42 | arrival:615→1170 |
| h6 | 1 | txn | shift_reservation | T55 | pickup:645→1195 |
| **h7** | 1 | txn | shift_reservation | S22 | checkin:685→1235 late_arrival:0→1 |
| h8 | 1 | txn | cancel_reservation | D55 | status:active→cancelled |
| h9 | 1 | txn | rebook_bundle | B97 | rebooked:0→1 |
| h10 | 2 | intervention | shift_reservation | F80 | arrival:900→990 |
| h11 | 2 | auto | shift_reservation | T21 | pickup:965→1010 |
| h12 | 2 | txn | shift_reservation | S57 | checkin:1015→1060 |
| h13 | 3 | intervention | shift_reservation | F14 | arrival:1095→1215 |
| h14 | 3 | auto | shift_reservation | T43 | pickup:1140→1235 |
| h15 | 3 | txn | shift_reservation | S93 | checkin:1180→1275 |
| h16 | 3 | txn | cancel_reservation | D40 | status:active→cancelled |
| h17 | 3 | txn | rebook_bundle | B62 | rebooked:0→1 |
| h18 | 4 | intervention | shift_reservation | F70 | arrival:630→870 |
| h19 | 4 | auto | shift_reservation | T24 | pickup:690→890 |
| h20 | 4 | txn | shift_reservation | S90 | checkin:710→910 |
| h21 | 5 | intervention | shift_reservation | F13 | arrival:1140→1080 |
| h22 | 5 | auto | shift_reservation | T64 | pickup:1200→1105 |
| h23 | 5 | txn | shift_reservation | S86 | checkin:1220→1125 |
| **h24** | 6 | intervention | shift_reservation | F80 | arrival:990→1290 |
| **h25** | 6 | auto | shift_reservation | T21 | pickup:1010→1310 ← corrupted in the incident |
| h26 | 6 | txn | shift_reservation | S57 | checkin:1060→1360 |
| h27 | 6 | txn | cancel_reservation | D81 | status:active→cancelled |

## 3. The corruption and the anomalous action

Corrupted record `h25` (key `auto_rebook[P51]`):
- clean: `h25 seg6 auto shift_reservation T21 rev=2 pickup:1010->1310`
- corrupted: `h25 seg6 txn shift_reservation T21 rev=2 pickup:1010->1310`

Forward learned graph on the clean history (correct):
- shift_reservation(S93, rev=1, {"checkin": 1470, "late_arrival": 1})

Forward learned graph on the corrupted history (the incident):
- shift_reservation(T43, rev=1, {"pickup": 1430})
- shift_reservation(S93, rev=1, {"checkin": 1470, "late_arrival": 1})

Anomalous objects handed to the auditor: T43

## 4. Backward trace through the same graph

Structural candidates (skeleton path from the source to the anomalous objects, policy witnesses on the path): h25, h24, h7, h5, h27, h17, h16, h13
Leave-one-out re-ranking (records whose masking changes the anomalous decisions first): **h25, h24, h7, h5, h27**
Rank of the corrupted record: 1

Non-graph baselines for the same incident: recency: h27, h26, h25 (gold rank 3); bm25_anomaly: h13, h14, h5 (gold rank —); source_heuristic: h15, h14, h13 (gold rank —)

## 5. Intervention: replace candidates with their clean versions and re-run the forward graph

| replaced records | EES restored | plan equals clean plan |
|---|---|---|
| top-1 predicted: h25 | yes | yes |
| top-3 predicted: h25, h24, h7 | yes | yes |
| matched random-1: h27 | no | no |
| matched random-3: h13, h27, h5 | no | no |
| most similar non-ancestor: h26 | no | no |
| most recent record: h27 | no | no |

## 6. The same incident at the actor level (DeepSeek-V4-Flash, graph_seg/verbose)

| history given to the actor | EES | legal |
|---|---|---|
| clean | 1 | 1 |
| corrupted | 1 | 1 |
| top3_replaced | 1 | 1 |
| random3_replaced | 1 | 1 |

Figure sketch: left, the event timeline (rows of §2) with the required witnesses highlighted and the corrupted one marked; middle, the intervention source and the anomalous objects with the skeleton path between them; right, the candidate list with the LOO ranking and the replacement outcomes of §5–§6.