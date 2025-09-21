# 🚀 Raspberry Pi NAS Server

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-2.0+-green.svg)
![RAID](https://img.shields.io/badge/RAID-10-red.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

**완전 자동화된 라즈베리파이 NAS 서버 구축 솔루션**

*RAID 10 + Samba + 웹 대시보드를 한 번에!*

</div>

---

## 📖 개요

이 프로젝트는 **라즈베리파이**에서 **4개의 SSD**를 사용하여 **RAID 10** 기반의 고성능 NAS 서버를 자동으로 구축하는 올인원 솔루션입니다.

### ✨ 주요 기능

- 🔧 **완전 자동화 설치**: 원클릭으로 모든 설정 완료
- 🛡️ **RAID 10**: 성능과 안정성을 동시에 확보
- 📁 **Samba 파일 서버**: 네트워크 파일 공유
- 📊 **웹 대시보드**: 실시간 시스템 모니터링
- 🦠 **ClamAV 바이러스 검사**: 자동 보안 검사
- 🔥 **방화벽 설정**: UFW 보안 구성
- 🔄 **Systemd 서비스**: 부팅 시 자동 시작

---

## 🖥️ 시스템 요구사항

### 하드웨어
- **라즈베리파이 4/5** (8GB 권장)
- **radsa penta sata hat** (sata SSD 연결용)
- **SSD 4개** (동일 용량 권장)
- **고품질 전원 어댑터** (12v DC 5525 power jack)

### 소프트웨어
- **Raspberry Pi OS** (64-bit)
- **Python 3.11+**
- **Root 권한** (sudo)

---

## 🚀 빠른 시작

### 1. 저장소 클론
```bash
git clone [https://github.com/epqlffltm/Pi-NAS-Builder.git]
cd raspberry-pi-nas
sudo apt update
sudo apt upgrade
```

### 2. 설정 파일 수정
```python
# 사용자 설정 영역 (스크립트 상단)
RAID_LEVEL = 10
RAID_DEVICES = ['/dev/sda', '/dev/sdb', '/dev/sdc', '/dev/sdd']
SAMBA_SHARE_NAME = "Public"
```

### 3. 자동 설치 실행
```bash
sudo python3 nas.py
```

### 4. 재부팅 후 계속
```bash
# PCIe 설정 후 재부팅됨
sudo python3 nas-setup.py  # 다시 실행
```

---

## 📊 웹 대시보드

설치 완료 후 다음 주소에서 대시보드에 접속할 수 있습니다:

```
http://[라즈베리파이-IP]:5000
```

### 대시보드 기능
- 📈 **실시간 RAID 상태** 모니터링
- 💾 **디스크 사용량** 확인  
- 🔧 **S.M.A.R.T 정보** (4개 디스크 전체)
- 🦠 **바이러스 검사 결과**
- 🔄 **30초 자동 새로고침**

---

## 📁 Samba 파일 공유

### Windows에서 접속
```
파일 탐색기 주소창: \\[라즈베리파이-IP]\Public
```

### macOS에서 접속
```
Finder > 이동 > 서버 연결: smb://[라즈베리파이-IP]/Public
```

### Linux에서 접속
```bash
sudo mount -t cifs //[라즈베리파이-IP]/Public /mnt/nas
```

---

## 🛠️ 관리 명령어

### 서비스 관리
```bash
# 대시보드 서비스
sudo systemctl start nas-dashboard     # 시작
sudo systemctl stop nas-dashboard      # 중지  
sudo systemctl restart nas-dashboard   # 재시작
sudo systemctl status nas-dashboard    # 상태 확인

# Samba 서비스
sudo systemctl restart smbd            # Samba 재시작
```

### 시스템 모니터링
```bash
# RAID 상태 확인
cat /proc/mdstat

# 디스크 사용량
df -h /home/[사용자]/storage

# 로그 확인  
sudo journalctl -u nas-dashboard -f

# S.M.A.R.T 정보 확인
sudo smartctl -a /dev/sda
```

---
<!--
## 📂 프로젝트 구조

```
raspberry-pi-nas/
├── nas-setup.py           # 메인 설치 스크립트
├── README.md              # 프로젝트 문서
├── LICENSE                # 라이선스 파일
├── screenshots/           # 스크린샷 폴더
│   ├── dashboard.png
│   └── raid-status.png
└── docs/                  # 추가 문서
    ├── troubleshooting.md
    └── advanced-config.md
```
-->
---

## 🔧 설정 옵션

### RAID 레벨 변경
```python
RAID_LEVEL = 0   # 성능 우선 (백업 없음)
RAID_LEVEL = 1   # 안정성 우선 (2개 디스크)  
RAID_LEVEL = 5   # 균형잡힌 선택 (3개 이상)
RAID_LEVEL = 10  # 최고 성능+안정성 (4개 이상)
```

### 파일 시스템 변경
```python
FILESYSTEM_TYPE = "ext4"   # 기본값 (권장)
FILESYSTEM_TYPE = "xfs"    # 대용량 파일용
FILESYSTEM_TYPE = "btrfs"  # 고급 기능용
```

---

## 📸 스크린샷

### 웹 대시보드
![Dashboard](screenshots/dashboard.png)

### RAID 상태
![RAID Status](screenshots/raid-status.png)

---

## ⚠️ 주의사항

### 중요한 경고
- 🔴 **데이터 손실 위험**: 기존 디스크의 모든 데이터가 삭제됩니다
- ⚡ **전원 공급**: 안정적인 전원 공급 필수 (RAID 동기화 중 전원 차단 금지)
- 🔧 **PCIe HAT**: config.txt 수정 후 반드시 재부팅 필요

### 권장사항
- ✅ 동일한 용량/모델의 SSD 사용 권장
- ✅ 정기적인 백업 수행
- ✅ UPS 사용 권장 (정전 대비)
- ✅ Radxa Penta SATA HAT 사용 권유(검증됨)

---

## 🐛 문제 해결

### 일반적인 문제들

#### SSD 인식 불가
```bash
# PCIe 설정 확인
sudo vim /boot/firmware/config.txt
# 다음 라인들이 있는지 확인:
# dtparam=pciex1
# dtparam=pciex1_gen=3
```

#### 대시보드 접속 불가
```bash
# 서비스 상태 확인
sudo systemctl status nas-dashboard
sudo journalctl -u nas-dashboard -f

# 포트 확인
sudo netstat -tlnp | grep 5000
```

#### RAID 동기화 실패
```bash
# RAID 상태 확인  
cat /proc/mdstat
sudo mdadm --detail /dev/md0

# 강제 재동기화
sudo mdadm --manage /dev/md0 --re-add /dev/sda
```
<!--
더 자세한 문제 해결은 [troubleshooting.md](docs/troubleshooting.md)를 참조하세요.
-->
---
<!--
## 🤝 기여하기

프로젝트 개선에 참여해주세요!

1. **Fork** 저장소
2. **Feature branch** 생성 (`git checkout -b feature/amazing-feature`)
3. **Commit** 변경사항 (`git commit -m 'Add amazing feature'`)
4. **Push** 브랜치 (`git push origin feature/amazing-feature`)
5. **Pull Request** 생성

---
-->

## 📄 라이선스

이 프로젝트는 [MIT License](LICENSE) 하에 배포됩니다.

---

## 👨‍💻 만든 사람

**Your Name**
- GitHub: [epqlffltm](https://github.com/epqlffltm)
- Email: epqlffltm.gmali.com
---

## 📞 지원

문제가 발생하면 다음 방법으로 도움을 받으세요:

- 📧 Email - epqlffltm@gmail.com

---

<div align="center">

**⭐ 이 프로젝트가 도움이 되었다면 Star를 눌러주세요! ⭐**

---

*Made with ❤️ for the Raspberry Pi community*

</div>
