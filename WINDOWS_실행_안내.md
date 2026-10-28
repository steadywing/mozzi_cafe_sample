# Windows PC에서 모찌카페 Docker 이미지 실행하기

이 안내는 Mac에서 만든 `linux/amd64` Docker 이미지를 Windows PC로 옮긴 **다음**에 사용하는 절차입니다. 명령어는 Windows **PowerShell**에서 실행합니다.

## 1. 준비할 파일과 환경

Mac의 원본 프로젝트에 있는 **`data` 폴더 자체를 폴더째 복사**해서, Docker 이미지 파일과 함께 Windows PC로 옮깁니다. `data` 안의 파일을 하나씩 골라 옮기거나 새 `data` 폴더를 만들어 일부 파일만 넣지 않습니다. Windows PC의 한 폴더에 다음과 같이 놓습니다.

```text
모찌카페-실행/
├─ wanted-cafe-chatbot.tar       # 전달받은 Docker 이미지
├─ data/                         # 원본 프로젝트의 data 폴더를 통째로 복사
│  ├─ menu.json
│  └─ embeddings/menu_images.faiss
└─ .env                          # 이 PC에서 작성할 API 키 파일
```

위의 `menu.json`과 `embeddings/menu_images.faiss`는 폴더 안에 들어 있는 파일의 **예시**입니다. 복사한 `data/`에는 원본 프로젝트의 고객·주문 자료, 카페 문서, 샘플 이미지 등 다른 파일과 하위 폴더도 그대로 있어야 합니다. Docker 이미지에는 `data/`와 API 키가 들어 있지 않습니다. 실행 중 바뀌는 대화·상태 기록도 옮긴 `data/` 폴더에 저장됩니다.

Docker Desktop을 설치하고 **WSL 2 백엔드**와 **Linux 컨테이너**를 사용합니다. NVIDIA GPU 드라이버도 설치합니다. 현재 이미지의 PyTorch는 CUDA 13 계열이므로 드라이버는 **R580 이상**이 필요합니다. PowerShell에서 `nvidia-smi`로 드라이버 버전을 확인할 수 있습니다.

이 폴더에 `.env` 파일을 만들고 사용할 기능의 키를 입력합니다. 파일 이름이 `.env.txt`가 되지 않도록 확인합니다.

```dotenv
OPENAI_API_KEY=실제_OpenAI_키
OPENAI_MODEL=gpt-5-nano
TYPESAFE_API_KEY=실제_TypeSafe_키
TYPESAFE_MODEL=jev-latest
GEMINI_API_KEY=영수증_포인트_기능을_쓸_때의_키
```

키가 없는 기능은 해당 모델 API를 호출할 때 실행되지 않습니다. `.env` 파일은 다른 사람에게 전달하지 않습니다.

## 2. 이미지 불러오기

PowerShell에서 위 폴더로 이동한 뒤 실행합니다. 아래 `C:\모찌카페-실행`은 예시이므로 실제 파일을 둔 경로로 바꿉니다.

```powershell
Set-Location 'C:\모찌카페-실행'
docker image load -i .\wanted-cafe-chatbot.tar
docker image inspect wanted-cafe-chatbot:cuda --format '{{.Os}}/{{.Architecture}}'
```

마지막 명령의 결과가 `linux/amd64`인지 확인합니다. 이미지가 보이지 않으면 `docker image ls`로 실제 불러온 이름과 태그를 확인합니다.

## 3. GPU 확인

```powershell
docker run --rm --gpus all wanted-cafe-chatbot:cuda python -c "import torch; print(torch.cuda.is_available())"
```

`True`가 나오면 컨테이너에서 GPU를 사용할 수 있습니다. `False`가 나오거나 실행이 실패하면 Docker Desktop의 WSL 2 백엔드, NVIDIA 드라이버, `nvidia-smi` 결과를 확인합니다.

## 4. 검색 모델 한 번 준비하기

상품 검색은 `google/embeddinggemma-2`를 컨테이너의 모델 캐시에서 읽습니다. Windows PC에 인터넷이 연결되어 있을 때 다음 명령을 **한 번** 실행합니다. 모델은 `wanted-cafe-hf`라는 Docker 볼륨에 저장되어, 컨테이너를 다시 만들어도 남습니다.

```powershell
docker run --rm --mount "type=volume,source=wanted-cafe-hf,target=/models/hf" wanted-cafe-chatbot:cuda python -c "from huggingface_hub import snapshot_download; snapshot_download('google/embeddinggemma-2')"
```

Windows PC가 인터넷에 연결되지 않았다면 이미지 파일만으로는 상품 검색을 실행할 수 없습니다. 모델 캐시를 별도로 옮겨 `wanted-cafe-hf` 볼륨에 넣는 준비가 필요합니다. 또한 Jev·OpenAI·Gemini 기능은 실행할 때 외부 API 연결이 필요합니다.

## 5. 서버 실행하기

먼저 현재 폴더와 데이터 파일을 확인합니다.

```powershell
Test-Path .\data\menu.json
Test-Path .\data\embeddings\menu_images.faiss
$projectPath = (Get-Location).Path
```

두 `Test-Path` 결과가 모두 `True`이면 서버를 실행합니다. 아래 명령의 각 줄 끝에 있는 PowerShell 역따옴표 뒤에는 공백을 넣지 않습니다.

```powershell
docker run -d --name wanted-cafe-chatbot --restart unless-stopped `
  --gpus all -p 127.0.0.1:8000:8000 --env-file .env `
  --mount "type=bind,source=$projectPath\data,target=/app/data" `
  --mount "type=volume,source=wanted-cafe-hf,target=/models/hf" `
  wanted-cafe-chatbot:cuda
```

브라우저에서 `http://localhost:8000/`을 열고, 서버 상태는 `http://localhost:8000/health`에서 확인합니다. 위 포트 설정은 이 PC에서만 접속하도록 열어 둡니다.

## 6. 상태 확인과 종료

```powershell
docker ps --filter "name=wanted-cafe-chatbot"
docker logs --tail 50 wanted-cafe-chatbot
docker inspect wanted-cafe-chatbot --format '{{.State.Health.Status}}'
docker stop wanted-cafe-chatbot
```

다시 시작할 때는 `docker start wanted-cafe-chatbot`을 실행합니다. 새 이미지 파일을 받았다면 기존 컨테이너를 `docker stop wanted-cafe-chatbot`과 `docker rm wanted-cafe-chatbot`으로 정리한 뒤, 2단계에서 새 이미지를 불러오고 5단계의 실행 명령을 다시 사용합니다. `data/` 폴더와 `wanted-cafe-hf` 볼륨은 그대로 둡니다.

## 참고

- [Docker 이미지 불러오기](https://docs.docker.com/reference/cli/docker/image/load/)
- [Windows Docker Desktop의 GPU 사용 조건](https://docs.docker.com/desktop/features/gpu/)
- [Docker의 호스트 폴더 연결](https://docs.docker.com/engine/storage/bind-mounts/)
- [Docker 볼륨 연결](https://docs.docker.com/engine/storage/volumes/)
- [CUDA 13 드라이버 호환성](https://docs.nvidia.com/cuda/archive/13.0.0/cuda-toolkit-release-notes/)
