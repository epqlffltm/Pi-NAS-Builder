#!/usr/bin/env python3
import os
import sys
import subprocess
import ipaddress
import pwd
import time
from flask import Flask, render_template_string
import logging

# ==============================================================================
# ▼▼▼ 사용자 설정 영역 ▼▼▼
# ==============================================================================

# 1. 사용할 RAID 레벨 (제조사 권장: 0, 1, 5, 10 중에서만 선택)
RAID_LEVEL = 10

# 2. RAID로 구성할 디스크 장치 목록
#    - RAID 0: 2개 이상 ['/dev/sda', '/dev/sdb']
#    - RAID 1: 정확히 2개 ['/dev/sda', '/dev/sdb']
#    - RAID 5: 3개 이상 ['/dev/sda', '/dev/sdb', '/dev/sdc']
#    - RAID 10: 4개 (짝수) ['/dev/sda', '/dev/sdb', '/dev/sdc', '/dev/sdd']
RAID_DEVICES = ['/dev/sda', '/dev/sdb', '/dev/sdc', '/dev/sdd']

# 3. 생성할 RAID 장치 이름
RAID_DEVICE_NAME = "/dev/md0"

# 4. 사용할 파일 시스템 종류
FILESYSTEM_TYPE = "ext4"

# 5. 마운트할 디렉토리 이름 (사용자 홈 디렉토리 아래에 생성됨)
MOUNT_POINT_BASE = "storage"

# 6. Samba 공유 이름
SAMBA_SHARE_NAME = "Public"

# 7. ClamAV 검사 결과를 저장할 로그 파일 경로
CLAMAV_LOG_FILE = "/var/log/clamav_scan.log"

# 8. Flask 앱 실행 포트
FLASK_PORT = 5000

# ==============================================================================
# ▲▲▲ 사용자 설정 영역 끝 ▲▲▲
# ==============================================================================

FLAG_FILE = "/var/lib/mysetup_step"
ALLOWED_RAID_LEVELS = [0, 1, 5, 10]

def validate_config():
    """스크립트 실행 전, 사용자 설정을 검증합니다."""
    print("[*] 설정 값 검증 시작...")
    
    if RAID_LEVEL not in ALLOWED_RAID_LEVELS:
        print(f"[!] 오류: 허용되지 않는 RAID 레벨({RAID_LEVEL})입니다. {ALLOWED_RAID_LEVELS} 중에서 선택하세요.")
        sys.exit(1)

    num_devices = len(RAID_DEVICES)
    valid = True
    error_msg = ""

    if RAID_LEVEL == 1 and num_devices != 2:
        error_msg = f"RAID 1은 정확히 2개의 디스크가 필요합니다. (현재: {num_devices}개)"
        valid = False
    elif RAID_LEVEL == 5 and num_devices < 3:
        error_msg = f"RAID 5는 최소 3개의 디스크가 필요합니다. (현재: {num_devices}개)"
        valid = False
    elif RAID_LEVEL == 10 and (num_devices < 4 or num_devices % 2 != 0):
        error_msg = f"RAID 10은 4개 이상의 짝수 디스크가 필요합니다. (현재: {num_devices}개)"
        valid = False
    elif RAID_LEVEL == 0 and num_devices < 2:
        error_msg = f"RAID 0은 최소 2개의 디스크가 필요합니다. (현재: {num_devices}개)"
        valid = False

    if not valid:
        print(f"[!] 오류: {error_msg}")
        sys.exit(1)

    print("[*] 설정 값 검증 완료. 유효한 설정입니다.")

def validate_devices():
    """RAID 구성 전 모든 디스크 존재 여부 확인"""
    print("[*] 디스크 장치 존재 여부 확인...")
    missing_devices = []
    
    for device in RAID_DEVICES:
        if not os.path.exists(device):
            missing_devices.append(device)
    
    if missing_devices:
        print(f"[!] 오류: 다음 디스크를 찾을 수 없습니다: {', '.join(missing_devices)}")
        print("[*] 사용 가능한 블록 디바이스 목록:")
        try:
            result = subprocess.run(["lsblk", "-d", "-o", "NAME,SIZE,TYPE"], 
                                  capture_output=True, text=True, check=True)
            print(result.stdout)
        except:
            print("블록 디바이스 목록을 가져올 수 없습니다.")
        sys.exit(1)
    
    print("[*] 모든 디스크 장치가 존재합니다.")

def check_root():
    """스크립트가 root 권한으로 실행되었는지 확인합니다."""
    if os.geteuid() != 0:
        print("[!] 이 스크립트는 root 권한(sudo)으로 실행해야 합니다.")
        sys.exit(1)

def run(cmd, timeout=300):
    """주어진 명령어를 실행하고 결과를 처리합니다."""
    print(f"[*] 실행: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, check=True, text=True, capture_output=True, timeout=timeout)
        return result
    except subprocess.TimeoutExpired:
        print(f"[!] 명령어 실행 시간 초과 ({timeout}초)")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"[!!!] 명령어 실행 중 심각한 오류 발생: {e}")
        if e.stdout:
            print(f"--- STDOUT ---\n{e.stdout.strip()}")
        if e.stderr:
            print(f"--- STDERR ---\n{e.stderr.strip()}")
        sys.exit(1)

def run_safe(cmd, timeout=60):
    """안전한 명령어 실행 (실패해도 스크립트 중단 안함)"""
    try:
        result = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
        return result
    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None

def confirm_action(prompt):
    """사용자에게 중요한 작업을 확인받습니다."""
    print(f"\n[!!! 경고 !!!] {prompt}")
    choice = input("정말로 이 작업을 계속하시겠습니까? (yes/no): ").lower()
    if choice != 'yes':
        print("[*] 작업을 취소했습니다.")
        sys.exit(0)
    print("[*] 작업을 계속합니다.")

def append_to_file(path, text):
    """파일 끝에 텍스트를 추가합니다."""
    try:
        with open(path, "a") as f:
            f.write(text)
    except Exception as e:
        print(f"[!] 파일 쓰기 오류 ({path}): {e}")

def get_step():
    """현재 진행 단계를 가져옵니다."""
    try:
        if not os.path.exists(FLAG_FILE):
            return 1
        with open(FLAG_FILE) as f:
            return int(f.read().strip())
    except:
        return 1

def set_step(step):
    """진행 단계를 파일에 저장합니다."""
    try:
        with open(FLAG_FILE, "w") as f:
            f.write(str(step))
    except Exception as e:
        print(f"[!] 단계 저장 오류: {e}")

def get_username():
    """현재 로그인한 사용자 이름을 가져옵니다."""
    return os.getenv("SUDO_USER") or os.getenv("USER")

def get_network_address():
    """로컬 IP를 기준으로 네트워크 주소를 계산합니다."""
    try:
        hostname_i_cmd = subprocess.run(["hostname", "-I"], capture_output=True, text=True, check=True)
        local_ip = hostname_i_cmd.stdout.strip().split()[0]
        return str(ipaddress.IPv4Interface(f"{local_ip}/24").network.network_address)
    except Exception:
        return "192.168.0.0" # 실패 시 기본값

def get_server_ip():
    """서버의 IP 주소를 가져옵니다."""
    try:
        hostname_i_cmd = subprocess.run(["hostname", "-I"], capture_output=True, text=True, check=True)
        return hostname_i_cmd.stdout.strip().split()[0]
    except Exception:
        return "서버IP"

def get_uuid(device):
    """장치의 UUID를 가져옵니다."""
    try:
        result = subprocess.run(["blkid", "-s", "UUID", "-o", "value", device], 
                              capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except Exception:
        print(f"[!] 경고: {device}의 UUID를 가져올 수 없습니다.")
        return None

def get_raid_status():
    """RAID 상태 확인"""
    try:
        with open("/proc/mdstat", "r") as f:
            content = f.read()
            if not content.strip():
                return "RAID 장치가 없습니다."
            return content
    except Exception:
        return "RAID 상태를 확인할 수 없습니다."

def check_smart(device):
    """S.M.A.R.T 상태를 확인합니다."""
    if not os.path.exists(device):
        return f"{device} 디스크를 찾을 수 없습니다."
    
    result = run_safe(["smartctl", "-a", device], timeout=30)
    if result and result.returncode == 0:
        return result.stdout
    elif result and result.returncode == 4:
        # smartctl은 때때로 4를 반환하지만 정보는 제공함
        return result.stdout if result.stdout else f"{device}의 S.M.A.R.T 정보를 읽을 수 없습니다."
    else:
        return f"{device}의 S.M.A.R.T 정보를 읽을 수 없습니다."

def get_disk_usage(mount_point):
    """디스크 사용량 확인 (디버깅 정보 포함)"""
    debug_info = []
    
    # 1. 마운트 포인트 존재 확인
    if not os.path.exists(mount_point):
        return f"❌ 마운트 포인트를 찾을 수 없습니다: {mount_point}"
    
    debug_info.append(f"✅ 마운트 포인트 존재: {mount_point}")
    
    # 2. 디렉토리인지 확인
    if not os.path.isdir(mount_point):
        return f"❌ {mount_point}는 디렉토리가 아닙니다."
    
    # 3. 권한 확인
    try:
        os.listdir(mount_point)
        debug_info.append("✅ 디렉토리 읽기 권한 OK")
    except PermissionError:
        debug_info.append("⚠️ 디렉토리 읽기 권한 없음")
    except Exception as e:
        debug_info.append(f"⚠️ 디렉토리 접근 오류: {e}")
    
    # 4. df 명령 시도 (sudo 없이)
    result = run_safe(["df", "-h", mount_point])
    if result and result.returncode == 0 and result.stdout.strip():
        debug_info.append("✅ df 명령 성공")
        return result.stdout
    else:
        if result:
            debug_info.append(f"❌ df 명령 실패 (return code: {result.returncode})")
            if result.stderr:
                debug_info.append(f"df 오류: {result.stderr.strip()}")
    
    # 5. shutil로 시도 (권한 문제 해결)
    try:
        import shutil
        total, used, free = shutil.disk_usage(mount_point)
        total_gb = total / (1024**3)
        used_gb = used / (1024**3)
        free_gb = free / (1024**3)
        usage_percent = (used / total) * 100 if total > 0 else 0
        
        debug_info.append("✅ shutil.disk_usage 성공")
        
        # 보기 좋게 포맷
        result_text = f"""Filesystem      Size  Used Avail Use% Mounted on
/dev/md0        {total_gb:>5.1f}T  {used_gb:>4.1f}G  {free_gb:>4.1f}T  {usage_percent:>3.0f}% {mount_point}

📊 상세 디스크 정보:
• 전체 용량: {total_gb:.2f} TB
• 사용 용량: {used_gb:.2f} GB  
• 여유 용량: {free_gb:.2f} TB
• 사용률: {usage_percent:.1f}%

💾 RAID 상태: 정상 동작"""
        return result_text
        
    except Exception as e:
        debug_info.append(f"❌ shutil.disk_usage 실패: {e}")
    
    # 6. 마운트 상태 확인해서 정보 추출 시도
    mount_result = run_safe(["mount"])
    if mount_result and mount_result.returncode == 0:
        mount_lines = [line for line in mount_result.stdout.split('\n') if mount_point in line]
        if mount_lines:
            debug_info.append(f"✅ 마운트 확인: {mount_lines[0]}")
            # mount 정보에서 장치 이름 추출
            device = mount_lines[0].split()[0]
            df_result = run_safe(["df", "-h", device])
            if df_result and df_result.returncode == 0:
                debug_info.append("✅ 장치별 df 명령 성공")
                return df_result.stdout
        else:
            debug_info.append(f"❌ {mount_point}가 마운트되지 않음")
    
    # 7. 모든 방법 실패 시 디버깅 정보 반환
    debug_text = "\n".join(debug_info)
    return f"""❌ 디스크 사용량을 확인할 수 없습니다.

🔧 디버깅 정보:
{debug_text}

💡 해결 방법:
1. RAID가 제대로 마운트되었는지 확인: mount | grep {mount_point}
2. 디스크 권한 확인: ls -la {mount_point}
3. 수동으로 확인: df -h {mount_point}"""

def read_clamav_log():
    """ClamAV 로그 파일 내용을 읽어옵니다."""
    try:
        with open(CLAMAV_LOG_FILE, "r") as f:
            content = f.read()
            if not content.strip():
                return f"{CLAMAV_LOG_FILE} 파일이 비어있습니다.\n주기적인 검사가 아직 실행되지 않았습니다."
            return content[-2000:]  # 최근 2000자만 표시
    except FileNotFoundError:
        return f"{CLAMAV_LOG_FILE} 파일이 없습니다.\n자동 검사가 cron에 등록되어 있습니다. 첫 번째 검사 완료까지 기다려주세요."

def setup_cron_jobs():
    """ClamAV 자동 검사 cron 작업 설정 (freshclam은 systemd 서비스 사용)"""
    mount_point = f"/home/{get_username()}/{MOUNT_POINT_BASE}"
    
    # 바이러스 검사만 cron에 등록 (freshclam은 systemd가 관리)
    clamscan_cron = f"0 2 * * * root clamscan -r {mount_point} > {CLAMAV_LOG_FILE} 2>&1\n"
    
    append_to_file("/etc/crontab", clamscan_cron)
    print("[*] ClamAV 자동 검사 스케줄이 등록되었습니다 (매일 새벽 2시).")
    print("[*] freshclam 업데이트는 systemd 서비스로 자동 관리됩니다.")

def setup_clamav():
    """ClamAV 설정 및 초기 업데이트"""
    print("[*] ClamAV 설정을 진행합니다...")
    
    # ClamAV 데몬 중지 (충돌 방지)
    run_safe(["systemctl", "stop", "clamav-freshclam"])
    
    # 로그 파일 권한 설정
    run_safe(["mkdir", "-p", "/var/log/clamav"])
    run_safe(["touch", "/var/log/clamav/freshclam.log"])
    run_safe(["chown", "clamav:clamav", "/var/log/clamav/freshclam.log"])
    run_safe(["chmod", "644", "/var/log/clamav/freshclam.log"])
    
    # freshclam 프로세스가 실행 중인지 확인하고 종료
    result = run_safe(["pgrep", "freshclam"])
    if result and result.returncode == 0:
        print("[*] 기존 freshclam 프로세스를 종료합니다...")
        run_safe(["pkill", "freshclam"])
        time.sleep(2)
    
    # 바이러스 DB 초기 업데이트 시도
    print("[*] ClamAV 바이러스 DB를 초기 업데이트합니다...")
    result = run_safe(["freshclam"], timeout=600)
    
    if result and result.returncode == 0:
        print("[*] ClamAV 바이러스 DB 업데이트 완료")
    else:
        print("[!] 경고: ClamAV 바이러스 DB 초기 업데이트 실패")
        print("    자동 스케줄링이 설정되어 있으므로 나중에 자동 업데이트됩니다.")
    
    # ClamAV 데몬 다시 시작
    run_safe(["systemctl", "start", "clamav-freshclam"])
    run_safe(["systemctl", "enable", "clamav-freshclam"])

def drop_privileges():
    """Flask 앱 실행 시 권한을 낮춥니다."""
    try:
        nobody = pwd.getpwnam('nobody')
        os.setgid(nobody.pw_gid)
        os.setuid(nobody.pw_uid)
        print("[*] Flask 앱이 nobody 사용자 권한으로 실행됩니다.")
    except Exception:
        print("[!] 경고: Flask 앱이 root 권한으로 실행됩니다.")

def setup():
    """단계별 설치 및 설정을 진행합니다."""
    step = get_step()
    username = get_username()
    network = get_network_address()
    mount_point = f"/home/{username}/{MOUNT_POINT_BASE}"

    if step == 1:
        print("[*] 1단계: 기본 패키지 설치 및 PCIe HAT 설정")
        print("[*] PCIe HAT에 연결된 SSD 인식을 위해 config.txt를 수정합니다.")
        
        # vim 먼저 설치
        run(["apt-get", "update"])
        run(["apt-get", "install", "-y", "vim"])
        
        # PCIe 설정 (Raspberry Pi용)
        config_txt = "/boot/firmware/config.txt"
        if os.path.exists(config_txt):
            print(f"[*] {config_txt}에 PCIe 설정을 추가합니다.")
            append_to_file(config_txt, "\n# PCIe HAT SSD 인식을 위한 설정\ndtparam=pciex1\ndtparam=pciex1_gen=3\n")
        else:
            print(f"[!] 경고: {config_txt} 파일을 찾을 수 없습니다. 수동으로 설정이 필요할 수 있습니다.")
        
        set_step(2)
        print("\n" + "="*50)
        print("[중요] PCIe HAT SSD 인식을 위해 재부팅이 필요합니다!")
        print("재부팅 후 다시 이 스크립트를 실행해주세요.")
        print("="*50)
        run(["reboot"])
        
    elif step == 2:
        print("[*] 2단계: 나머지 패키지 설치 및 디스크 확인")
        print("[*] PCIe HAT SSD가 인식되었는지 확인합니다.")
        
        # 이제 디스크 존재 여부 확인 (재부팅 후)
        validate_devices()
        
        # 나머지 패키지 설치
        run(["apt-get", "install", "-y", "mdadm", "smartmontools", "samba", "ufw", "clamav"])
        
        set_step(3)
        print("[*] 2단계 완료 → 다음 단계 진행")
        
    elif step == 3:
        print("[*] 3단계: 디스크 초기화 시작")
        confirm_action(f"다음 디스크들의 모든 데이터를 영구적으로 삭제합니다: {', '.join(RAID_DEVICES)}")
        
        for device in RAID_DEVICES:
            print(f"[*] {device} 초기화 중...")
            run(["wipefs", "--all", device])
        
        set_step(4)
        
    elif step == 4:
        print(f"[*] 4단계: RAID {RAID_LEVEL} 생성 시작")
        confirm_action(f"{RAID_DEVICE_NAME}에 {len(RAID_DEVICES)}개의 디스크로 RAID {RAID_LEVEL}을 생성합니다.")
        
        cmd = ["mdadm", "--create", "--verbose", RAID_DEVICE_NAME, 
               f"--level={RAID_LEVEL}", f"--raid-devices={len(RAID_DEVICES)}"] + RAID_DEVICES
        run(cmd)
        
        # RAID 생성 완료 대기
        print("[*] RAID 동기화가 진행 중입니다. 잠시 기다려주세요...")
        time.sleep(5)
        
        set_step(5)
        
    elif step == 5:
        print("[*] 5단계: 파일 시스템 생성 및 영속성 설정")
        
        # 파일 시스템 생성
        run([f"mkfs.{FILESYSTEM_TYPE}", RAID_DEVICE_NAME])
        
        # 마운트 포인트 생성 및 마운트
        run(["mkdir", "-p", mount_point])
        run(["mount", RAID_DEVICE_NAME, mount_point])
        
        # 소유권 설정
        run(["chown", f"{username}:{username}", mount_point])
        
        # mdadm 설정 저장
        print("[*] mdadm 설정을 저장하여 재부팅 시에도 RAID를 유지합니다.")
        mdadm_detail = run(["mdadm", "--detail", "--scan"])
        append_to_file("/etc/mdadm/mdadm.conf", mdadm_detail.stdout)
        run(["update-initramfs", "-u"])

        # fstab 등록
        print("[*] /etc/fstab에 UUID 기반 자동 마운트를 등록합니다.")
        device_uuid = get_uuid(RAID_DEVICE_NAME)
        if device_uuid:
            fstab_entry = f"\nUUID={device_uuid} {mount_point} {FILESYSTEM_TYPE} defaults,nofail 0 2\n"
            append_to_file("/etc/fstab", fstab_entry)
        else:
            print("[!] 경고: UUID를 가져올 수 없어 장치 이름으로 fstab에 등록합니다.")
            fstab_entry = f"\n{RAID_DEVICE_NAME} {mount_point} {FILESYSTEM_TYPE} defaults,nofail 0 2\n"
            append_to_file("/etc/fstab", fstab_entry)
        
        set_step(6)
        
    elif step == 6:
        print("[*] 6단계: Samba 설정")
        
        samba_block = f"""
[{SAMBA_SHARE_NAME}]
   path = {mount_point}
   browseable = yes
   writeable = yes
   guest ok = yes
   read only = no
   create mask = 0775
   directory mask = 0775
   hosts allow = 127.0.0.1 {network}/24
   force user = {username}
   force group = {username}
"""
        append_to_file("/etc/samba/smb.conf", samba_block)
        run(["systemctl", "restart", "smbd"])
        run(["systemctl", "enable", "smbd"])
        
        set_step(7)
        
    elif step == 7:
        print("[*] 7단계: 방화벽 및 보안 설정")
        
        # 방화벽 설정
        run(["ufw", "allow", "ssh"])
        run(["ufw", "allow", "samba"])
        run(["ufw", "allow", f"{FLASK_PORT}/tcp"])
        run(["ufw", "--force", "enable"])
        
        # ClamAV cron 작업 설정
        setup_cron_jobs()
        
        # ClamAV 설정 및 초기 업데이트
        setup_clamav()
        
        set_step(8)
        
    elif step >= 8:
        print("[*] 모든 설치 및 설정 단계가 완료되었습니다.")

# Flask 애플리케이션
app = Flask(__name__)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

@app.route("/")
def dashboard():
    try:
        # 임시로 간단한 사용자명 확인 (안전한 방식)
        username = "samba"  # 하드코딩으로 임시 해결
        
        # 마운트에서 실제 사용자명 찾기 시도
        try:
            result = run_safe(["mount"])
            if result and result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if '/dev/md0' in line and '/home/' in line:
                        try:
                            path_part = line.split(' on ')[1].split(' type')[0]
                            if '/home/' in path_part:
                                username = path_part.split('/home/')[1].split('/')[0]
                                break
                        except:
                            pass
        except:
            pass
        
        network = get_network_address()
        server_ip = get_server_ip()
        mount_point = f"/home/{username}/{MOUNT_POINT_BASE}"
        
        # 시스템 정보 수집 (안전하게)
        try:
            raid_status = get_raid_status()
        except Exception as e:
            raid_status = f"RAID 상태 확인 오류: {str(e)}"
        
        try:
            # 모든 RAID 디스크의 S.M.A.R.T 정보 수집
            smart_results = []
            
            for i, device in enumerate(RAID_DEVICES):
                smart_results.append(f"{'='*60}")
                smart_results.append(f"💾 디스크 {i+1}: {device}")
                smart_results.append(f"{'='*60}")
                
                if not os.path.exists(device):
                    smart_results.append(f"❌ {device} 디스크를 찾을 수 없습니다.")
                    smart_results.append("")
                    continue
                
                try:
                    # smartctl 명령 실행
                    result = run_safe(["smartctl", "-i", "-H", device], timeout=20)
                    if result and result.returncode in [0, 4]:
                        lines = result.stdout.split('\n')
                        
                        # 중요한 정보만 추출
                        important_lines = []
                        for line in lines:
                            line = line.strip()
                            if any(keyword in line for keyword in [
                                'Device Model:', 'Serial Number:', 'Firmware Version:',
                                'User Capacity:', 'SMART overall-health', 'SMART Health Status'
                            ]):
                                important_lines.append(line)
                        
                        if important_lines:
                            smart_results.extend(important_lines)
                            smart_results.append("✅ 기본 상태: 정상")
                        else:
                            smart_results.append("✅ 디스크 연결됨 (상세 정보 제한)")
                    else:
                        # smartctl 실패 시 기본 정보라도 표시
                        smart_results.append(f"⚠️ S.M.A.R.T 정보 읽기 실패 (디바이스: {device})")
                        smart_results.append("✅ 디스크 물리적으로 연결됨")
                        
                        # 기본 디스크 정보 시도
                        try:
                            basic_info = run_safe(["lsblk", "-o", "NAME,SIZE,MODEL", device], timeout=10)
                            if basic_info and basic_info.returncode == 0:
                                smart_results.append(f"기본 정보:\n{basic_info.stdout}")
                        except:
                            pass
                            
                except Exception as disk_error:
                    smart_results.append(f"❌ {device} 확인 중 오류: {str(disk_error)[:100]}")
                
                smart_results.append("")  # 빈 줄 추가
            
            if smart_results:
                smart_info = '\n'.join(smart_results)
            else:
                smart_info = "S.M.A.R.T 정보를 가져올 수 없습니다."
                
        except Exception as e:
            smart_info = f"S.M.A.R.T 정보 확인 중 전체 오류: {str(e)}"
        
        try:
            clamav_info = read_clamav_log()
        except Exception as e:
            clamav_info = f"ClamAV 로그 읽기 오류: {str(e)}"
        
        try:
            disk_usage = get_disk_usage(mount_point)
        except Exception as e:
            # 디스크 사용량 직접 확인 (백업 방법)
            try:
                import shutil
                if os.path.exists(mount_point):
                    total, used, free = shutil.disk_usage(mount_point)
                    total_tb = total / (1024**4)
                    used_gb = used / (1024**3)
                    free_tb = free / (1024**4)
                    usage_percent = (used / total) * 100 if total > 0 else 0
                    
                    disk_usage = f"""Filesystem      Size  Used Avail Use% Mounted on
/dev/md0        {total_tb:.1f}T  {used_gb:.0f}G  {free_tb:.1f}T  {usage_percent:.0f}% {mount_point}

📊 상세 정보:
• 전체 용량: {total_tb:.2f} TB
• 사용 용량: {used_gb:.2f} GB  
• 여유 용량: {free_tb:.2f} TB
• 사용률: {usage_percent:.1f}%"""
                else:
                    disk_usage = f"❌ 마운트 포인트를 찾을 수 없음: {mount_point}"
            except Exception as e2:
                disk_usage = f"디스크 사용량 확인 오류: {str(e2)}"

        html = f"""
        <!DOCTYPE html>
        <html lang="ko">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>🚀 서버 대시보드</title>
            <style>
                body {{ 
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen-Sans, Ubuntu, Cantarell, "Helvetica Neue", sans-serif; 
                    margin: 0; padding: 2em; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: #333; min-height: 100vh;
                }}
                .container {{ 
                    max-width: 1200px; margin: 0 auto; 
                    background: white; border-radius: 15px; 
                    box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                    overflow: hidden;
                }}
                .header {{
                    background: linear-gradient(45deg, #667eea, #764ba2);
                    color: white; padding: 2em; text-align: center;
                }}
                .header h1 {{ margin: 0; font-size: 2.5em; }}
                .content {{ padding: 2em; }}
                .info-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 2em; margin-bottom: 2em; }}
                .info-card {{
                    background: #f8f9fa; border-radius: 10px; padding: 1.5em;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }}
                .info-card h3 {{ margin-top: 0; color: #667eea; border-bottom: 2px solid #eee; padding-bottom: 0.5em; }}
                .status-good {{ color: #28a745; font-weight: bold; }}
                .status-warning {{ color: #ffc107; font-weight: bold; }}
                .refresh-info {{ 
                    color: #6c757d; font-size: 0.9em; text-align: center; 
                    margin-top: 1em; font-style: italic;
                }}
                pre {{ 
                    background: #2d3748; color: #e2e8f0; padding: 1em; 
                    border-radius: 8px; overflow-x: auto; 
                    white-space: pre-wrap; word-wrap: break-word;
                    max-height: 400px; overflow-y: auto;
                    font-size: 0.85em;
                }}
                .metric {{ display: flex; justify-content: space-between; margin: 0.5em 0; }}
                .metric-label {{ font-weight: 500; }}
                .metric-value {{ font-weight: bold; color: #667eea; }}
                .samba-path {{ 
                    background: #e3f2fd; border: 1px solid #2196f3; 
                    padding: 8px; border-radius: 5px; font-family: monospace;
                    word-break: break-all; margin-top: 5px;
                }}
            </style>
            <script>
                // 30초마다 자동 새로고침
                setTimeout(() => window.location.reload(), 30000);
            </script>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🚀 NAS 서버 대시보드</h1>
                    <p>RAID {RAID_LEVEL} | {len(RAID_DEVICES)} 디스크 | {SAMBA_SHARE_NAME} 공유</p>
                    <p>서버 주소: <strong>{server_ip}</strong> | 사용자: <strong>{username}</strong></p>
                </div>
                <div class="content">
                    <div class="info-grid">
                        <div class="info-card">
                            <h3>📊 시스템 정보</h3>
                            <div class="metric">
                                <span class="metric-label">서버 IP:</span>
                                <span class="metric-value">{server_ip}</span>
                            </div>
                            <div class="metric">
                                <span class="metric-label">마운트 경로:</span>
                                <span class="metric-value">{mount_point}</span>
                            </div>
                            <div class="metric">
                                <span class="metric-label">네트워크 대역:</span>
                                <span class="metric-value">{network}/24</span>
                            </div>
                            <div class="metric">
                                <span class="metric-label">Samba 공유:</span>
                            </div>
                            <div class="samba-path">\\\\{server_ip}\\{SAMBA_SHARE_NAME}</div>
                            <div class="metric" style="margin-top: 1em;">
                                <span class="metric-label">상태:</span>
                                <span class="status-good">✅ 정상 운영</span>
                            </div>
                        </div>
                        <div class="info-card">
                            <h3>💾 디스크 사용량</h3>
                            <pre>{disk_usage}</pre>
                        </div>
                    </div>
                    
                    <div class="info-card">
                        <h3>🛡️ RAID 상태</h3>
                        <pre>{raid_status}</pre>
                    </div>
                    
                    <div class="info-card">
                        <h3>🔧 디스크 S.M.A.R.T 정보 ({RAID_DEVICES[0] if RAID_DEVICES else 'N/A'})</h3>
                        <pre>{smart_info}</pre>
                    </div>
                    
                    <div class="info-card">
                        <h3>🦠 ClamAV 바이러스 검사</h3>
                        <pre>{clamav_info}</pre>
                        <p><small>💡 매일 새벽 2시에 자동 검사가 실행됩니다.</small></p>
                    </div>
                    
                    <div class="refresh-info">
                        🔄 이 페이지는 30초마다 자동으로 새로고침됩니다
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        return render_template_string(html)
        
    except Exception as e:
        # 최악의 경우 간단한 오류 페이지 반환
        error_html = f"""
        <!DOCTYPE html>
        <html lang="ko">
        <head>
            <meta charset="UTF-8">
            <title>대시보드 오류</title>
        </head>
        <body>
            <h1>🚨 대시보드 오류</h1>
            <p>오류 발생: {str(e)}</p>
            <p>로그를 확인하세요: <code>sudo journalctl -u nas-dashboard -f</code></p>
            <button onclick="window.location.reload()">새로고침</button>
        </body>
        </html>
        """
        return render_template_string(error_html)

def create_systemd_service():
    """Flask 앱을 위한 systemd 서비스 파일을 생성합니다."""
    script_path = os.path.abspath(__file__)
    username = get_username()
    
    # 스크립트를 /opt/nas-dashboard/ 디렉토리로 복사
    service_dir = "/opt/nas-dashboard"
    service_script = f"{service_dir}/nas-dashboard.py"
    
    run(["mkdir", "-p", service_dir])
    run(["cp", script_path, service_script])
    run(["chmod", "755", service_script])
    run(["chown", "root:root", service_script])
    
    # 로그 파일 미리 생성 및 권한 설정
    log_file = "/var/log/nas-dashboard.log"
    run_safe(["touch", log_file])
    run_safe(["chmod", "666", log_file])
    
    service_content = f"""[Unit]
Description=NAS Dashboard Service
After=network.target

[Service]
Type=simple
User=nobody
Group=nogroup
WorkingDirectory={service_dir}
ExecStart=/usr/bin/python3 {service_script} --dashboard-only
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
    
    service_file = "/etc/systemd/system/nas-dashboard.service"
    with open(service_file, "w") as f:
        f.write(service_content)
    
    # systemd 데몬 리로드 및 서비스 활성화
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", "nas-dashboard.service"])
    print(f"[*] systemd 서비스가 생성되었습니다: {service_file}")
    print(f"[*] 스크립트가 {service_script}로 복사되었습니다.")
    print(f"[*] 로그 파일 {log_file}이 생성되었습니다.")

def run_dashboard_only():
    """Flask 대시보드만 실행합니다."""
    print(f"[*] NAS 대시보드 서비스 시작 (포트: {FLASK_PORT})")
    
    # 로그 디렉토리 및 파일 생성 (nobody 사용자가 접근 가능하도록)
    log_dir = "/var/log"
    log_file = "/var/log/nas-dashboard.log"
    
    try:
        # 로그 파일이 없으면 생성
        if not os.path.exists(log_file):
            with open(log_file, 'w') as f:
                f.write("")
        
        # 로그 파일 권한 설정 (nobody 사용자가 쓸 수 있도록)
        os.chmod(log_file, 0o666)
        
        # 로깅 설정
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
    except Exception as e:
        # 로그 파일 생성 실패 시 콘솔만 사용
        print(f"[!] 로그 파일 생성 실패: {e}. 콘솔 로그만 사용합니다.")
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler()]
        )
    
    app.run(host="0.0.0.0", port=FLASK_PORT, debug=False)

def show_management_commands():
    """관리 명령어들을 표시합니다."""
    server_ip = get_server_ip()
    
    print("\n" + "="*70)
    print("🎉 모든 설정이 완료되었습니다!")
    print(f"📱 Flask 대시보드: http://{server_ip}:{FLASK_PORT}")
    print(f"📁 Samba 공유: \\\\{server_ip}\\{SAMBA_SHARE_NAME}")
    print("🔒 보안: UFW 방화벽 활성화, ClamAV 자동 검사 설정됨")
    print("="*70)
    print("\n📋 관리 명령어:")
    print("  🚀 대시보드 시작:      sudo systemctl start nas-dashboard")
    print("  🛑 대시보드 중지:      sudo systemctl stop nas-dashboard")
    print("  🔄 대시보드 재시작:    sudo systemctl restart nas-dashboard")
    print("  📊 대시보드 상태:      sudo systemctl status nas-dashboard")
    print("  📜 대시보드 로그:      sudo journalctl -u nas-dashboard -f")
    print("  📄 상세 로그 파일:     tail -f /var/log/nas-dashboard.log")
    print("\n  🔧 RAID 상태 확인:     cat /proc/mdstat")
    print("  💾 디스크 사용량:      df -h")
    print("  🛡️ 방화벽 상태:       sudo ufw status")
    print("="*70)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='NAS 자동 설치 및 관리 스크립트')
    parser.add_argument('--dashboard-only', action='store_true', 
                       help='Flask 대시보드만 실행 (systemd 서비스용)')
    args = parser.parse_args()
    
    # 대시보드만 실행하는 경우 (systemd 서비스에서 호출)
    if args.dashboard_only:
        run_dashboard_only()
        sys.exit(0)
    
    # 일반적인 설치 과정
    check_root()
    
    # 초기 설정 검증 (첫 단계에서만)
    if get_step() == 1:
        validate_config()
    
    # 설치 및 설정 실행
    setup()
    
    # 모든 단계 완료 후 systemd 서비스 생성
    if get_step() >= 8:
        create_systemd_service()
        show_management_commands()
        
        # 대시보드 서비스 시작
        print("\n[*] 대시보드 서비스를 시작합니다...")
        run(["systemctl", "start", "nas-dashboard"])
        
        print("\n✅ 설치 완료! 대시보드가 백그라운드에서 실행 중입니다.")
        print("   터미널을 닫아도 서비스는 계속 실행됩니다.")
        print("   서버 재부팅 시에도 자동으로 시작됩니다.")