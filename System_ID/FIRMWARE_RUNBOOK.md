# 통신 어댑터 펌웨어 교체 — 실행 절차서 (2026-09-09)

> 사용자가 직접 실행하는 부분이 있어, **그대로 복사해 붙일 수 있게** 적습니다.
> 각 명령이 무엇을 왜 하는지 함께 적습니다. 줄임말을 쓰지 않습니다.

## 왜 하는가 (한 문단)

지금 벤치의 통신 어댑터는 **초당 230~240개의 프레임**밖에 못 보냅니다. 그런데 프레임 하나를
주고받는 시간은 **0.93 밀리초**로 빠릅니다. 데이터를 0바이트로 줄여도 초당 프레임 수가 그대로
였으므로(240 대 230), 막는 것은 **글자 수가 아니라 프레임 하나당 드는 고정 비용**입니다.
프레임당 4.3 밀리초가 드는데, 이 어댑터가 붙은 USB 저속 구간의 한 칸이 1 밀리초이니
**한 프레임에 USB 칸 네 개**를 쓰는 셈입니다.

새 펌웨어(candleLight)는 **여러 프레임을 USB 패킷 하나에 묶어** 보냅니다. 즉 우리가 실측으로
확인한 바로 그 지점을 겨냥합니다. 글자 수를 줄이는 방향은 아무 소용이 없다는 것도 같은
측정으로 확인했습니다.

## 실행 가능한지 — 확인 끝난 것

| 확인 항목 | 결과 |
|---|---|
| 어댑터의 마이크로컨트롤러 | **STM32F042C6** (지금 펌웨어 소스의 링커 파일이 `STM32F042C6_FLASH.ld`) |
| 새 펌웨어에 맞는 대상 이름 | **`canable_fw`** (candleLight 의 STM32F042C6 대상) |
| 새 펌웨어 빌드 | ✅ 성공. 23,596 바이트 = 32 KB 중 71.8% |
| **되돌릴 펌웨어** | ✅ **지금 올라간 것과 같은 커밋(`9fddea4`)에서 빌드 성공**, 29,888 바이트 |
| 로봇 커널의 `gs_usb` | ✅ 이미 있음 — 새 펌웨어를 올리면 바로 잡힘 |
| `dfu-util` | 로봇에 없음 → 설치 파일을 옮겨 뒀습니다 |
| 파일 위치 (로봇) | `/home/syaro/System_ID/fw/` |

**되돌릴 수 없게 되는 경우는 하나뿐입니다** — BOOT 점퍼에 손이 닿지 않는 경우. STM32 의 DFU
부트로더는 **지울 수 없는 ROM 에** 있어서, 잘못된 펌웨어를 올려도 부트로더는 그대로 남습니다.
즉 **BOOT 점퍼로 다시 들어갈 수만 있으면 몇 번이든 되돌릴 수 있습니다.**

## 사용자가 먼저 확인해 주실 것 (여기서 막히면 진행 불가)

1. **어댑터에 BOOT 점퍼나 버튼이 있는지.** 케이스를 열어야 보일 수 있습니다. 사진에서 보이는
   점퍼는 종단저항(120 Ω)이라 다른 것입니다.
2. **여분 어댑터가 있는지.** 지금 이것이 유일한 통로입니다.

## 절차

### 0단계 — 준비 (사람)

```bash
ssh syaro@10.8.0.14
sudo dpkg -i /home/syaro/System_ID/fw/dfu-util_0.11-1_amd64.deb
dfu-util --version        # 0.11 이 나오면 성공
```

인터넷이 없는 로봇이라 파일로 설치합니다. 의존하는 라이브러리(`libusb-1.0-0`)는 이미
깔려 있는 것을 확인했습니다.

### 1단계 — 지금 상태 정리 (사람)

```bash
sudo pkill slcand          # 어댑터를 붙잡고 있는 프로그램을 놓아 준다
ls /dev/ttyACM0            # 아직 보이면 정상
```

로봇 프로그램(`huphy_remote_motion`)은 이미 멈춰 있습니다. 카메라 서버는 다른 장치라 그대로
둬도 됩니다.

### 2단계 — DFU 로 들어가기 (사람, 물리 작업)

**어댑터를 뽑고 → BOOT 점퍼를 꽂거나 버튼을 누른 채 → 다시 꽂습니다.**

```bash
lsusb | grep -i 'STM32\|0483:df11'
```

`STM32 BOOTLOADER` 또는 `0483:df11` 이 보이면 성공입니다. 안 보이면 **여기서 멈추고**
점퍼 위치를 다시 확인하세요 — 이 상태가 아니면 아무것도 쓸 수 없습니다.

### 3단계 — 지금 펌웨어를 읽어 백업 (사람, 되면 좋고 안 돼도 진행 가능)

```bash
sudo dfu-util -a 0 -s 0x08000000:32768 -U /home/syaro/System_ID/fw/backup_original.bin
```

읽기 잠금이 걸려 있으면 실패합니다. 실패해도 괜찮습니다 — 같은 커밋에서 빌드한 파일이 이미
있습니다(`canable-9fddea4.bin`). 성공하면 그 둘을 비교해 볼 수 있어 더 확실합니다.

### 4단계 — 어떤 칩인지 눈으로 확인 (사람)

```bash
sudo dfu-util -l
```

`@Internal Flash /0x08000000/032*001Kg` 처럼 **32 KB** 로 나오면 STM32F042C6 이 맞습니다.
**128 KB(128*001Kg)로 나오면 멈추세요** — 그건 STM32F072 이고 다른 파일이 필요합니다.
(저에게 알려 주시면 그 대상으로 다시 빌드하겠습니다.)

### 5단계 — 새 펌웨어 쓰기 (사람)

```bash
sudo dfu-util -a 0 -s 0x08000000:leave -D /home/syaro/System_ID/fw/canable_fw.bin
```

끝나면 어댑터를 **뽑았다가 BOOT 점퍼를 원래대로 되돌리고** 다시 꽂습니다.

### 6단계 — 잡혔는지 확인 (사람)

```bash
lsusb | grep -i canable        # 이제 gs_usb 장치로 보입니다
dmesg | tail -5 | grep -i can
ip link show | grep can
```

**중요 — 여기서부터 CAN 을 켜는 방법이 바뀝니다.** 예전에는 `slcand` 로 문자열 장치를
CAN 인 척 만들었지만, 이제는 커널이 직접 CAN 장치로 인식합니다:

```bash
# 예전 (더 이상 안 씀)
# sudo slcand -o -c -s8 /dev/ttyACM0 can0

# 새 방법
sudo ip link set can0 up type can bitrate 1000000
sudo ip link set can0 txqueuelen 1000     # 예전엔 10 이었음 - 몰아 보낼 때 넘치던 원인
ip -d link show can0                      # bitrate 1000000 이 보이면 성공
```

### 7단계 — 빨라졌는지 재기 (제가 합니다)

말씀만 주시면 제가 같은 시험을 그대로 돌려 **230/s 가 얼마로 바뀌었는지** 보고하겠습니다.
모터는 건드리지 않고 쓰지 않는 번호로만 보내는 시험입니다.

## 되돌리기 (언제든)

2단계로 DFU 에 다시 들어간 뒤:

```bash
sudo dfu-util -a 0 -s 0x08000000:leave -D /home/syaro/System_ID/fw/canable-9fddea4.bin
```

그리고 원래대로:

```bash
sudo slcand -o -c -s8 /dev/ttyACM0 can0
sudo ip link set can0 up
```

## 로봇 프로그램 되살리기 (필요할 때)

```bash
cd /home/syaro/Human-Pygmalion && nohup .venv-huphy/bin/python3 -u -m \
  pygviewer.bridge.huphy_remote_motion \
  --config /home/syaro/Human-Pygmalion/HUPHY/config/robot_bench.yaml \
  --cache ./cache --variant LegOnly-AB --map pygviewer/bridge/joint_map_biped.json \
  --limb left_leg --enable hip_yaw,knee --arm-token 1b897fd1558c4bc0 \
  --listen 0.0.0.0:9872 --telemetry 192.168.20.177:9870 \
  --kp-max 50 --kd-max 2.5 --deadman-s 0.2 --hold-s 86400 --return-s 2 \
  --allow-uncalibrated > /home/syaro/remote_motion.log 2>&1 &
```

---

# 딸린 시험 — 가상머신이 얼마나 먹는가

**이건 위 펌웨어 교체가 기대만큼 안 될 때만 하시면 됩니다.** 새 펌웨어로 초당 1000회가
넘게 나오면 가상머신은 애초에 문제가 아니었던 것이므로 이 시험이 필요 없습니다.

## 왜 하는가

로봇은 가상머신입니다(QEMU, 가상 CPU 4개, virtio 랜 = Proxmox 계열로 보임). USB 장치가
가상머신으로 넘어갈 때 매 전송이 하이퍼바이저를 왕복하는데, 이것이 프레임당 4.3 밀리초의
큰 몫일 수 있습니다. **같은 어댑터를 호스트에서 직접 재면 그 몫이 갈립니다.**

## 호스트에서 치실 명령

```bash
# 1. 가상머신에서 USB 어댑터를 뗀다 (웹 화면: VM → 하드웨어 → USB 장치 → 제거)
#    또는 명령으로 (VMID 는 로봇 가상머신 번호):
qm set <VMID> --delete usb0

# 2. 호스트에 도구가 있는지
which slcand cangen || apt install -y can-utils

# 3. 호스트에서 어댑터를 CAN 으로 올린다 (지금 로봇에서 하던 것과 같은 방식)
modprobe can slcan
slcand -o -c -s8 /dev/ttyACM0 can0
ip link set can0 up

# 4. 던지기 시험 — 모터가 쓰지 않는 번호(0x123)로만 보낸다.
#    다른 노드가 확인응답은 해주므로 버스 오류가 안 나고, 번호가 달라 모터는 무시한다.
#    모터 토크는 지금 꺼져 있다.
time cangen can0 -g 0 -n 2000 -I 123 -L 8
```

마지막 줄의 **걸린 시간을 알려 주시면** 제가 초당 몇 개인지 계산해 비교하겠습니다.
지금 가상머신 안에서 잰 값은 **초당 230.5개**(같은 8바이트 프레임)입니다.

* 호스트에서도 230 근처면 → **어댑터/펌웨어 문제**, 가상머신은 무죄
* 호스트에서 훨씬 빠르면 → **가상머신 통과가 범인**, 제어를 실물 기판으로 옮기는 것이 답

## 끝나면 되돌리기

```bash
ip link set can0 down
pkill slcand
# 웹 화면에서 USB 장치를 가상머신에 다시 붙인다 (또는 qm set <VMID> -usb0 host=ad50:60c4)
```

---

## 나중에 — 라즈베리파이 전용 기판

사용자가 "나중에 로봇 전용으로 라즈베리파이를 셋업하겠다"고 하셨습니다. 그때 바뀌는 것:

* 가상머신 통과가 사라집니다 (위 시험의 답이 무엇이든 이 몫은 없어짐)
* **SPI 연결 CAN 이 그때부터 가능해집니다** — 가상머신에는 SPI 버스가 없어서 지금은 불가
* 다만 **MCP2515 는 8 MHz 크리스털 품을 사면 안 됩니다.** 비트 하나를 최소 8조각으로 나눠야
  하는데 8 MHz 에서는 4조각밖에 안 나와 **1 Mbps 가 규격상 성립하지 않습니다**(500 kbps 까지).
  16 MHz 이상, 또는 **MCP2518FD**(CAN-FD, 큰 버퍼)를 권합니다.
