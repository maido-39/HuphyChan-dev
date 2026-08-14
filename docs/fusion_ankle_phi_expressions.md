# Fusion 파라메트릭 — 발목 크랭크 가동각 폐형식 (2026-08-14, 기계정밀도 검증)

용도: Fusion 사용자 파라미터에 붙여넣으면 설계치(ankle_*) 변경 시 크랭크 중립각·±가동각 자동 갱신.
도출/검증: docs/76 §10c (일반식·분기 증명·코너 지배·오차 ≤7e-15°). 각도 상수는 `deg` 단위 필수.
φ 기준: 크랭크핀이 피벗 +y(뒤/앵커쪽) 수평 = 0°, 위로 +. 모터B 식은 미러(roll 부호 반전)가 이미 반영된 코너 상수 사용.

| 파라미터 | 값 | 지배 자세(pitch, roll) |
|---|---|---|
| ankle_phiA_neutral | −19.05° | (0, 0) |
| ankle_phiA_max | +27.18° | (−50, −20) |
| ankle_phiA_min | −61.87° | (+30, +20) |
| ankle_phiB_neutral | −14.24° | (0, 0) |
| ankle_phiB_max | +35.41° | (−50, +20) |
| ankle_phiB_min | −55.93° | (+30, −20) |


## ankle_phiA_max  (= 27.181 deg; pose pitch -50, roll -20)
```
atan(((-cos(-50 deg)*sin(-20 deg)*ankle_RP_r - sin(-50 deg)*ankle_RP_AB_L - cos(-50 deg)*cos(-20 deg)*ankle_RP_h) - (ankle_B2RP + CONS_ankle_A2B))/(-sin(-50 deg)*sin(-20 deg)*ankle_RP_r + cos(-50 deg)*ankle_RP_AB_L - sin(-50 deg)*cos(-20 deg)*ankle_RP_h)) + acos((((-sin(-50 deg)*sin(-20 deg)*ankle_RP_r + cos(-50 deg)*ankle_RP_AB_L - sin(-50 deg)*cos(-20 deg)*ankle_RP_h)^2 + ((-cos(-50 deg)*sin(-20 deg)*ankle_RP_r - sin(-50 deg)*ankle_RP_AB_L - cos(-50 deg)*cos(-20 deg)*ankle_RP_h) - (ankle_B2RP + CONS_ankle_A2B))^2 + ankle_A_r^2 - (ankle_A_L^2 - ((cos(-20 deg)*ankle_RP_r - sin(-20 deg)*ankle_RP_h) - ankle_AB_h)^2)) / (2*ankle_A_r))/sqrt((-sin(-50 deg)*sin(-20 deg)*ankle_RP_r + cos(-50 deg)*ankle_RP_AB_L - sin(-50 deg)*cos(-20 deg)*ankle_RP_h)^2 + ((-cos(-50 deg)*sin(-20 deg)*ankle_RP_r - sin(-50 deg)*ankle_RP_AB_L - cos(-50 deg)*cos(-20 deg)*ankle_RP_h) - (ankle_B2RP + CONS_ankle_A2B))^2))
```

## ankle_phiA_neutral  (= -19.053 deg; pose pitch 0, roll 0)
```
atan(((-cos(0 deg)*sin(0 deg)*ankle_RP_r - sin(0 deg)*ankle_RP_AB_L - cos(0 deg)*cos(0 deg)*ankle_RP_h) - (ankle_B2RP + CONS_ankle_A2B))/(-sin(0 deg)*sin(0 deg)*ankle_RP_r + cos(0 deg)*ankle_RP_AB_L - sin(0 deg)*cos(0 deg)*ankle_RP_h)) + acos((((-sin(0 deg)*sin(0 deg)*ankle_RP_r + cos(0 deg)*ankle_RP_AB_L - sin(0 deg)*cos(0 deg)*ankle_RP_h)^2 + ((-cos(0 deg)*sin(0 deg)*ankle_RP_r - sin(0 deg)*ankle_RP_AB_L - cos(0 deg)*cos(0 deg)*ankle_RP_h) - (ankle_B2RP + CONS_ankle_A2B))^2 + ankle_A_r^2 - (ankle_A_L^2 - ((cos(0 deg)*ankle_RP_r - sin(0 deg)*ankle_RP_h) - ankle_AB_h)^2)) / (2*ankle_A_r))/sqrt((-sin(0 deg)*sin(0 deg)*ankle_RP_r + cos(0 deg)*ankle_RP_AB_L - sin(0 deg)*cos(0 deg)*ankle_RP_h)^2 + ((-cos(0 deg)*sin(0 deg)*ankle_RP_r - sin(0 deg)*ankle_RP_AB_L - cos(0 deg)*cos(0 deg)*ankle_RP_h) - (ankle_B2RP + CONS_ankle_A2B))^2))
```

## ankle_phiA_min  (= -61.874 deg; pose pitch 30, roll 20)
```
atan(((-cos(30 deg)*sin(20 deg)*ankle_RP_r - sin(30 deg)*ankle_RP_AB_L - cos(30 deg)*cos(20 deg)*ankle_RP_h) - (ankle_B2RP + CONS_ankle_A2B))/(-sin(30 deg)*sin(20 deg)*ankle_RP_r + cos(30 deg)*ankle_RP_AB_L - sin(30 deg)*cos(20 deg)*ankle_RP_h)) + acos((((-sin(30 deg)*sin(20 deg)*ankle_RP_r + cos(30 deg)*ankle_RP_AB_L - sin(30 deg)*cos(20 deg)*ankle_RP_h)^2 + ((-cos(30 deg)*sin(20 deg)*ankle_RP_r - sin(30 deg)*ankle_RP_AB_L - cos(30 deg)*cos(20 deg)*ankle_RP_h) - (ankle_B2RP + CONS_ankle_A2B))^2 + ankle_A_r^2 - (ankle_A_L^2 - ((cos(20 deg)*ankle_RP_r - sin(20 deg)*ankle_RP_h) - ankle_AB_h)^2)) / (2*ankle_A_r))/sqrt((-sin(30 deg)*sin(20 deg)*ankle_RP_r + cos(30 deg)*ankle_RP_AB_L - sin(30 deg)*cos(20 deg)*ankle_RP_h)^2 + ((-cos(30 deg)*sin(20 deg)*ankle_RP_r - sin(30 deg)*ankle_RP_AB_L - cos(30 deg)*cos(20 deg)*ankle_RP_h) - (ankle_B2RP + CONS_ankle_A2B))^2))
```

## ankle_phiB_max  (= 35.407 deg; pose pitch -50, roll 20)
```
atan(((-cos(-50 deg)*sin(-20 deg)*ankle_RP_r - sin(-50 deg)*ankle_RP_AB_L - cos(-50 deg)*cos(-20 deg)*ankle_RP_h) - ankle_B2RP)/(-sin(-50 deg)*sin(-20 deg)*ankle_RP_r + cos(-50 deg)*ankle_RP_AB_L - sin(-50 deg)*cos(-20 deg)*ankle_RP_h)) + acos((((-sin(-50 deg)*sin(-20 deg)*ankle_RP_r + cos(-50 deg)*ankle_RP_AB_L - sin(-50 deg)*cos(-20 deg)*ankle_RP_h)^2 + ((-cos(-50 deg)*sin(-20 deg)*ankle_RP_r - sin(-50 deg)*ankle_RP_AB_L - cos(-50 deg)*cos(-20 deg)*ankle_RP_h) - ankle_B2RP)^2 + ankle_B_r^2 - (ankle_B_L^2 - ((cos(-20 deg)*ankle_RP_r - sin(-20 deg)*ankle_RP_h) - ankle_AB_h)^2)) / (2*ankle_B_r))/sqrt((-sin(-50 deg)*sin(-20 deg)*ankle_RP_r + cos(-50 deg)*ankle_RP_AB_L - sin(-50 deg)*cos(-20 deg)*ankle_RP_h)^2 + ((-cos(-50 deg)*sin(-20 deg)*ankle_RP_r - sin(-50 deg)*ankle_RP_AB_L - cos(-50 deg)*cos(-20 deg)*ankle_RP_h) - ankle_B2RP)^2))
```

## ankle_phiB_neutral  (= -14.242 deg; pose pitch 0, roll 0)
```
atan(((-cos(0 deg)*sin(0 deg)*ankle_RP_r - sin(0 deg)*ankle_RP_AB_L - cos(0 deg)*cos(0 deg)*ankle_RP_h) - ankle_B2RP)/(-sin(0 deg)*sin(0 deg)*ankle_RP_r + cos(0 deg)*ankle_RP_AB_L - sin(0 deg)*cos(0 deg)*ankle_RP_h)) + acos((((-sin(0 deg)*sin(0 deg)*ankle_RP_r + cos(0 deg)*ankle_RP_AB_L - sin(0 deg)*cos(0 deg)*ankle_RP_h)^2 + ((-cos(0 deg)*sin(0 deg)*ankle_RP_r - sin(0 deg)*ankle_RP_AB_L - cos(0 deg)*cos(0 deg)*ankle_RP_h) - ankle_B2RP)^2 + ankle_B_r^2 - (ankle_B_L^2 - ((cos(0 deg)*ankle_RP_r - sin(0 deg)*ankle_RP_h) - ankle_AB_h)^2)) / (2*ankle_B_r))/sqrt((-sin(0 deg)*sin(0 deg)*ankle_RP_r + cos(0 deg)*ankle_RP_AB_L - sin(0 deg)*cos(0 deg)*ankle_RP_h)^2 + ((-cos(0 deg)*sin(0 deg)*ankle_RP_r - sin(0 deg)*ankle_RP_AB_L - cos(0 deg)*cos(0 deg)*ankle_RP_h) - ankle_B2RP)^2))
```

## ankle_phiB_min  (= -55.930 deg; pose pitch 30, roll -20)
```
atan(((-cos(30 deg)*sin(20 deg)*ankle_RP_r - sin(30 deg)*ankle_RP_AB_L - cos(30 deg)*cos(20 deg)*ankle_RP_h) - ankle_B2RP)/(-sin(30 deg)*sin(20 deg)*ankle_RP_r + cos(30 deg)*ankle_RP_AB_L - sin(30 deg)*cos(20 deg)*ankle_RP_h)) + acos((((-sin(30 deg)*sin(20 deg)*ankle_RP_r + cos(30 deg)*ankle_RP_AB_L - sin(30 deg)*cos(20 deg)*ankle_RP_h)^2 + ((-cos(30 deg)*sin(20 deg)*ankle_RP_r - sin(30 deg)*ankle_RP_AB_L - cos(30 deg)*cos(20 deg)*ankle_RP_h) - ankle_B2RP)^2 + ankle_B_r^2 - (ankle_B_L^2 - ((cos(20 deg)*ankle_RP_r - sin(20 deg)*ankle_RP_h) - ankle_AB_h)^2)) / (2*ankle_B_r))/sqrt((-sin(30 deg)*sin(20 deg)*ankle_RP_r + cos(30 deg)*ankle_RP_AB_L - sin(30 deg)*cos(20 deg)*ankle_RP_h)^2 + ((-cos(30 deg)*sin(20 deg)*ankle_RP_r - sin(30 deg)*ankle_RP_AB_L - cos(30 deg)*cos(20 deg)*ankle_RP_h) - ankle_B2RP)^2))
```

