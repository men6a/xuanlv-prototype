# ---------- 替换下面的 generate_variant 函数 ----------
def generate_variant(melody_stream, surprise_strength=0.3):
    """
    生成旋律变体（增强音乐性版本）
    规则：
      - 保持在 C 大调音阶内
      - 音程跳进不超过五度
      - 节奏保持简单（只改变为常见时值）
      - 通过 surprise_strength 控制改动幅度
    """
    # 定义 C 大调音阶的 MIDI 模 12 集合
    C_MAJOR_SCALE = {0, 2, 4, 5, 7, 9, 11}  # C, D, E, F, G, A, B
    # 常见时值（以四分音符为1）
    COMMON_DURS = [0.5, 1, 2]  # 八分、四分、二分

    # 提取原始音符
    original_notes = list(melody_stream.getElementsByClass(note.Note))
    if not original_notes:
        return stream.Stream()

    # 深拷贝音符
    import copy
    new_notes = [copy.deepcopy(n) for n in original_notes]

    # 确定要改动的音符数量
    n_changes = max(1, int(len(new_notes) * surprise_strength))

    for _ in range(n_changes):
        idx = random.randint(0, len(new_notes)-1)
        current_note = new_notes[idx]
        current_pitch = current_note.pitch.midi
        current_dur = current_note.quarterLength

        # 决定是改音高还是改节奏（随机）
        if random.random() < 0.7:  # 70% 概率改音高
            # 尝试生成新音高
            attempts = 0
            new_pitch = None
            while attempts < 10:
                # 根据 surprise_strength 决定步长
                step = random.choice([-2, -1, 1, 2]) if surprise_strength > 0.5 else random.choice([-1, 1])
                candidate = current_pitch + step
                # 检查是否在调内（C大调）
                if (candidate % 12) in C_MAJOR_SCALE and 0 <= candidate <= 127:
                    # 检查音程跳进（与前后音符）
                    prev_pitch = new_notes[idx-1].pitch.midi if idx > 0 else candidate
                    next_pitch = new_notes[idx+1].pitch.midi if idx < len(new_notes)-1 else candidate
                    interval_to_prev = abs(candidate - prev_pitch)
                    interval_to_next = abs(candidate - next_pitch)
                    # 跳进不超过五度（7个半音）
                    if interval_to_prev <= 7 and interval_to_next <= 7:
                        new_pitch = candidate
                        break
                attempts += 1
            if new_pitch is not None:
                current_note.pitch.midi = new_pitch
        else:  # 30% 概率改节奏
            # 将时值改为另一个常见时值（避免变成三连音等）
            if current_dur in COMMON_DURS:
                new_dur = random.choice([d for d in COMMON_DURS if d != current_dur])
                current_note.quarterLength = new_dur

        # 高意外强度时，偶尔允许更大的改动（如五度跳进）
        if surprise_strength > 0.8 and random.random() < 0.3:
            # 尝试五度跳进（7个半音）
            leap = random.choice([-7, 7])
            candidate = current_pitch + leap
            if (candidate % 12) in C_MAJOR_SCALE and 0 <= candidate <= 127:
                # 检查是否与前后音符形成不协和（简单处理：只检查是否太近？）
                current_note.pitch.midi = candidate

    # 构建新流
    new_stream = stream.Stream()
    for n in new_notes:
        new_stream.append(n)
    return new_stream
# ---------- 替换结束 ----------
