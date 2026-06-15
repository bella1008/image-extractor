import time
from datetime import datetime
import os


def run_test_agent(file_path):
    print("Test Agent: 1분(60초) 대기 중...")
    time.sleep(60)

    # 지정된 포맷으로 현재 시간 가져오기
    now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    log_message = f"{now} Test ok\n"

    # 'a' (append) 모드로 열어서 파일 끝에 로그 추가
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(log_message)

    print(f"Test Agent: 로그 작성 완료 -> {log_message.strip()}")


if __name__ == "__main__":
    # 두 에이전트가 공유할 로그 파일 이름
    shared_log_file = "agent_communication.txt"
    run_test_agent(shared_log_file)
    