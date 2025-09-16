# AHN_Snap-Recorder
OpenCV + PySide6 GUI video recorder (Preview/Record, Snapshot, Enter-to-Connect)

OpenCV와 PySide6를 활용한 실시간 비디오 녹화 및 스냅샷 도구입니다. 웹캠과 IP 카메라를 지원하며, 직관적인 GUI와 키보드 단축키를 제공합니다.

## ✨ 주요 기능

### 기본 기능
- **실시간 카메라 영상 표시**: OpenCV의 `cv2.VideoCapture`를 이용하여 카메라 영상 실시간 출력
- **동영상 파일 저장**: OpenCV의 `cv2.VideoWriter`를 이용한 동영상 파일 생성
- **Preview/Record 모드**: 
  - Preview 모드: 실시간 미리보기만 표시
  - Record 모드: 화면에 빨간색 원(●)과 녹화 시간 표시
- **키보드 제어**:
  - `Space`: Preview ↔ Record 모드 전환
  - `ESC`: 프로그램 종료

### 추가 기능
- **코덱 자동 탐색**: 시스템 호환성에 따라 MJPG/XVID/MP4V 코덱 자동 선택
- **스냅샷 기능**: 현재 프레임을 PNG 파일로 저장 (`S` 키)
- **FPS 조정**: 캡처된 FPS에 따른 자동 조정 (1-30fps 범위)
- **IP 카메라 지원**: RTSP 프로토콜을 통한 원격 카메라 연결
- **GUI 인터페이스**: PySide6 기반 사용자 친화적 인터페이스
- **실시간 상태 표시**: 해상도, FPS, 녹화 시간 오버레이
- **폴백 모드**: 코덱 실패 시 개별 프레임 저장 및 FFmpeg 변환 가이드

## 🔧 시스템 요구사항

### Python 환경
- Python 3.8 이상
- OpenCV 4.x 
- PySide6 6.x

### 기본 조작
1. **소스 연결**: 
   - 웹캠: `0` (기본값)
   - IP 카메라: `rtsp://id:pw@ip/stream` 형식
   - `Enter` 키 또는 Connect 버튼으로 연결

2. **녹화 제어**:
   - `Space` 키 또는 REC 버튼으로 녹화 시작/중지
   - 녹화 중 빨간 원(●) 표시 및 경과 시간 표시

3. **스냅샷**: `S` 키 또는 Snapshot 버튼으로 현재 프레임 저장

4. **종료**: `ESC` 키 또는 Exit 버튼

### 키보드 단축키
| 키 | 기능 |
|---|---|
| `Enter` | 소스 연결 |
| `Space` | 녹화 시작/중지 |
| `S` | 스냅샷 |
| `ESC` | 프로그램 종료 |


## 🎬 스크린샷 및 데모

### Preview 모드
![Preview Mode](assets/screenshot_main2.png)
*실시간 카메라 영상 미리보기*

### Record 모드
![Record Mode](assets/screenshot_main1.png)
*녹화 중 - 빨간 원과 타이머 표시*

### 데모 영상 : 실제 녹화 영상 샘플
![Demo](assets/rec_20250915_234256.gif)
