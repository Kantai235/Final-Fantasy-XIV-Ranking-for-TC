#!/usr/bin/env bash

set -euo pipefail
shopt -s nullglob

# GitHub-hosted runner 每個 job 都從乾淨映像啟動；若每輪都用 apt 安裝
# fonts-noto-cjk，就會重複下載約 61 MB，且 Ubuntu mirror 暫時降速時會拖住
# 整個部署。workflow 會快取此使用者字型目錄；本腳本只有在字型檔不存在時
# 才下載套件，並只抽出 OG SVG 實際使用的 Sans Regular / Bold 兩個 TTC。
readonly FONT_PACKAGE="fonts-noto-cjk"
readonly FONT_DIR="${OG_FONT_DIR:-${HOME}/.local/share/fonts/ffxiv-og}"
readonly REGULAR_FONT_PATH="${FONT_DIR}/NotoSansCJK-Regular.ttc"
readonly BOLD_FONT_PATH="${FONT_DIR}/NotoSansCJK-Bold.ttc"
readonly SYSTEM_FONT_DIR="/usr/share/fonts/opentype/noto"
readonly TEMP_ROOT="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
readonly MAX_ATTEMPTS=3
readonly COMMAND_TIMEOUT_SECONDS=120
DOWNLOADED_FONT_DEB=""

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "::error::準備 OG 圖中文字型需要 ${command_name}，但目前 runner 找不到此命令。"
    exit 1
  fi
}

copy_required_fonts() {
  local source_dir="$1"

  install -d "$FONT_DIR"
  install -m 0644 "${source_dir}/NotoSansCJK-Regular.ttc" "$REGULAR_FONT_PATH"
  install -m 0644 "${source_dir}/NotoSansCJK-Bold.ttc" "$BOLD_FONT_PATH"
}

run_apt_update() {
  local attempt

  for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1)); do
    echo "更新 APT 套件索引（第 ${attempt}/${MAX_ATTEMPTS} 次）。"
    if timeout --signal=TERM --kill-after=10s "${COMMAND_TIMEOUT_SECONDS}s" \
      sudo apt-get \
        -o Acquire::Retries=2 \
        -o Acquire::http::Timeout=30 \
        -o Acquire::https::Timeout=30 \
        update; then
      return 0
    fi

    echo "::warning::APT 套件索引更新未在 ${COMMAND_TIMEOUT_SECONDS} 秒內完成，準備重試。"
    sleep $((attempt * 5))
  done

  echo "::error::APT 套件索引更新已重試 ${MAX_ATTEMPTS} 次，仍無法完成。"
  return 1
}

download_font_package() {
  local download_root="$1"
  local attempt
  local attempt_dir
  local -a deb_files

  for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1)); do
    attempt_dir="${download_root}/attempt-${attempt}"
    install -d "$attempt_dir"
    echo "下載 ${FONT_PACKAGE}（第 ${attempt}/${MAX_ATTEMPTS} 次，每次最多 ${COMMAND_TIMEOUT_SECONDS} 秒）。"

    if (
      cd "$attempt_dir"
      timeout --signal=TERM --kill-after=10s "${COMMAND_TIMEOUT_SECONDS}s" \
        apt-get \
          -o Acquire::Retries=2 \
          -o Acquire::http::Timeout=30 \
          -o Acquire::https::Timeout=30 \
          download "$FONT_PACKAGE"
    ); then
      deb_files=("${attempt_dir}"/fonts-noto-cjk_*.deb)
      if [[ ${#deb_files[@]} -eq 1 && -s "${deb_files[0]}" ]]; then
        DOWNLOADED_FONT_DEB="${deb_files[0]}"
        return 0
      fi
    fi

    echo "::warning::${FONT_PACKAGE} 未在時限內完整下載，改用新的暫存目錄重試。" >&2
    sleep $((attempt * 5))
  done

  echo "::error::${FONT_PACKAGE} 已重試 ${MAX_ATTEMPTS} 次，仍無法完整下載。" >&2
  return 1
}

register_and_verify_fonts() {
  local regular_match
  local bold_match

  fc-cache -f "$FONT_DIR"
  regular_match="$(fc-match -f '%{family}|%{style}|%{file}\n' 'Noto Sans CJK TC:style=Regular')"
  bold_match="$(fc-match -f '%{family}|%{style}|%{file}\n' 'Noto Sans CJK TC:style=Bold')"

  # OG SVG 在 Linux 明確指定 TTC 內的實際 family；Regular 與 Bold 都必須可被
  # fontconfig 解析。runner 未來若預載同版字型，命中系統副本也屬正確結果。
  if [[ "$regular_match" != *"Noto Sans CJK TC"* || "$bold_match" != *"Noto Sans CJK TC"* ]]; then
    echo "::error::fontconfig 未完整辨識 Noto Sans CJK TC：Regular=${regular_match:-無結果}；Bold=${bold_match:-無結果}"
    return 1
  fi

  echo "OG 圖中文字型已可使用：Regular=${regular_match}；Bold=${bold_match}"
}

require_command apt-get
require_command dpkg-deb
require_command fc-cache
require_command fc-match
require_command install
require_command timeout

if [[ -s "$REGULAR_FONT_PATH" && -s "$BOLD_FONT_PATH" ]]; then
  echo "已從 Actions cache 還原 OG 圖中文字型，略過 APT 下載。"
elif [[ -s "${SYSTEM_FONT_DIR}/NotoSansCJK-Regular.ttc" && -s "${SYSTEM_FONT_DIR}/NotoSansCJK-Bold.ttc" ]]; then
  # runner 映像未來若預載 Noto CJK，直接複製即可；不必為了建立專案快取再次下載。
  echo "runner 已預載 Noto CJK，複製必要字型到使用者字型目錄。"
  copy_required_fonts "$SYSTEM_FONT_DIR"
else
  download_root="$(mktemp -d "${TEMP_ROOT%/}/ffxiv-og-fonts.XXXXXX")"
  extract_dir="${download_root}/extracted"

  run_apt_update
  download_font_package "$download_root"
  install -d "$extract_dir"
  dpkg-deb --extract "$DOWNLOADED_FONT_DEB" "$extract_dir"
  copy_required_fonts "${extract_dir}/usr/share/fonts/opentype/noto"
fi

register_and_verify_fonts
