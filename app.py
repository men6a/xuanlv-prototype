import streamlit as st
import pandas as pd
import numpy as np
import tempfile
import random
import copy
import base64
import re
import math
from music21 import converter, note, stream, midi, chord, interval, pitch, meter, instrument

st.set_page_config(page_title="玄·律标注原型", layout="wide")

# 隐藏页面加载遮罩
st.markdown("""
<style>
.stApp::before {
    display: none !important;
}
</style>
""", unsafe_allow_html=True)

# 全局字体调小
st.markdown("""
<style>
html, body, [class*="css"]  {
    font-size: 0.9rem;
}
.main-title {
    font-size: 1.4rem;
    font-weight: bold;
    margin-bottom: 1rem;
}
.stSlider label {
    font-size: 0.9rem !important;
}
/* 侧边栏标题字体更小 */
.sidebar .sidebar-content h3 {
    font-size: 0.75rem !important;
    font-weight: 600;
}
/* 按钮极限贴近感受输入框 */
.button-row {
    margin-top: -18px !important;
}
.button-row .stButton button, .button-row .stDownloadButton button {
    font-size: 0.8rem !important;
    padding: 0.15rem 0.4rem !important;
    line-height: 1.2;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">🎵 玄·律标注原型</div>', unsafe_allow_html=True)
st.markdown("上传MIDI文件，从动机发展出带左手伴奏的完整乐段，并标注听感。")

# 初始化session_state
if 'variants' not in st.session_state:
    st.session_state.variants = []
if 'variant_meta' not in st.session_state:
    st.session_state.variant_meta = []
if 'labels_surprise' not in st.session_state:
    st.session_state.labels_surprise = []
if 'labels_beauty' not in st.session_state:
    st.session_state.labels_beauty = []
if 'labels_feelings' not in st.session_state:
    st.session_state.labels_feelings = []
if 'save_indicator' not in st.session_state:
    st.session_state.save_indicator = []

# ==================== 全维度音乐理论规则库 ====================

class MusicTheoryEngine:
    """音乐理论引擎：整合最新研究成果"""
    
    # 1. 调式音阶定义（包含西方五声调式）
    SCALES = {
        # 西方大小调
        'major': [0, 2, 4, 5, 7, 9, 11],        # 大调
        'minor': [0, 2, 3, 5, 7, 8, 10],        # 自然小调
        'harmonic_minor': [0, 2, 3, 5, 7, 8, 11], # 和声小调
        'melodic_minor': [0, 2, 3, 5, 7, 9, 11],  # 旋律小调上行
        
        # 中古调式
        'dorian': [0, 2, 3, 5, 7, 9, 10],       # 多利亚
        'mixolydian': [0, 2, 4, 5, 7, 9, 10],   # 混合利底亚
        
        # 西方五声调式
        'major_pentatonic': [0, 2, 4, 7, 9],     # 大调五声：1 2 3 5 6
        'minor_pentatonic': [0, 3, 5, 7, 10],    # 小调五声：1 b3 4 5 b7
        
        # 中国五声调式（宫商角徵羽）
        'gong': [0, 2, 4, 7, 9],        # 宫调式（同大调五声）
        'shang': [2, 4, 7, 9, 11],      # 商调式
        'jue': [4, 7, 9, 11, 14],       # 角调式
        'zhi': [7, 9, 11, 14, 16],      # 徵调式
        'yu': [9, 11, 14, 16, 18],      # 羽调式
    }
    
    # 2. 音程协和度矩阵
    CONSONANCE_MATRIX = {
        0: 1.0, 12: 1.0,
        7: 0.9, 19: 0.9,
        5: 0.8, 17: 0.8,
        4: 0.8, 3: 0.75, 16: 0.8, 15: 0.75,
        9: 0.7, 8: 0.65, 21: 0.7, 20: 0.65,
        2: 0.4, 10: 0.4, 14: 0.4, 22: 0.4,
        1: 0.1, 11: 0.1, 13: 0.1, 23: 0.1,
        6: 0.0, 18: 0.0
    }
    
    @classmethod
    def get_scale_notes(cls, key, mode):
        """获取指定调性的音阶音符（MIDI模12）"""
        note_to_idx = {'C':0, 'C#':1, 'Db':1, 'D':2, 'D#':3, 'Eb':3, 'E':4, 
                      'F':5, 'F#':6, 'Gb':6, 'G':7, 'G#':8, 'Ab':8, 'A':9, 
                      'A#':10, 'Bb':10, 'B':11}
        root = note_to_idx.get(key, 0)
        scale_pattern = cls.SCALES.get(mode, cls.SCALES['major'])
        return {(root + interval) % 12 for interval in scale_pattern}
    
    @classmethod
    def roman_or_num_to_degree(cls, token):
        """将罗马数字或阿拉伯数字转换为度数（0=I）"""
        token = token.strip()
        if token.isdigit():
            num = int(token)
            if 1 <= num <= 7:
                return num - 1
        roman_map = {
            'I': 0, 'II': 1, 'III': 2, 'IV': 3, 'V': 4, 'VI': 5, 'VII': 6,
            'i': 0, 'ii': 1, 'iii': 2, 'iv': 3, 'v': 4, 'vi': 5, 'vii': 6
        }
        base = re.match(r'^[IiVv]+', token)
        if base:
            return roman_map.get(base.group(), 0)
        return 0
    
    @classmethod
    def get_chord_tones(cls, chord_degree, key='C', mode='major'):
        """获取和弦内音（大三和弦）"""
        note_to_idx = {'C':0, 'C#':1, 'Db':1, 'D':2, 'D#':3, 'Eb':3, 'E':4, 
                      'F':5, 'F#':6, 'Gb':6, 'G':7, 'G#':8, 'Ab':8, 'A':9, 
                      'A#':10, 'Bb':10, 'B':11}
        root_idx = note_to_idx.get(key, 0)
        degree_to_interval = [0, 2, 4, 5, 7, 9, 11]
        if chord_degree >= len(degree_to_interval):
            chord_degree = chord_degree % 7
        root_pitch_class = (root_idx + degree_to_interval[chord_degree]) % 12
        return {(root_pitch_class + offset) % 12 for offset in [0, 4, 7]}
    
    @classmethod
    def get_chord_notes(cls, chord_degree, key='C', mode='major', octave=3):
        """获取和弦的具体音符（MIDI值列表），用于分解或琶音"""
        root = cls.get_bass_note(chord_degree, key, mode, octave)
        third = root + 4
        fifth = root + 7
        return [root, third, fifth]
    
    @classmethod
    def get_bass_note(cls, chord_degree, key='C', mode='major', octave=3):
        """获取和弦根音MIDI值"""
        note_to_idx = {'C':0, 'C#':1, 'Db':1, 'D':2, 'D#':3, 'Eb':3, 'E':4, 
                      'F':5, 'F#':6, 'Gb':6, 'G':7, 'G#':8, 'Ab':8, 'A':9, 
                      'A#':10, 'Bb':10, 'B':11}
        root_idx = note_to_idx.get(key, 0)
        degree_to_interval = [0, 2, 4, 5, 7, 9, 11]
        if chord_degree >= len(degree_to_interval):
            chord_degree = chord_degree % 7
        pitch_class = (root_idx + degree_to_interval[chord_degree]) % 12
        return octave * 12 + pitch_class
    
    @classmethod
    def interval_consonance(cls, interval):
        interval = abs(interval) % 12
        return cls.CONSONANCE_MATRIX.get(interval, 0.5)
    
    @classmethod
    def adjust_to_scale(cls, pitch, scale_notes):
        """将音高调整到最近的调内音"""
        if (pitch % 12) in scale_notes:
            return pitch
        best = pitch
        min_dist = 12
        for sn in scale_notes:
            for octave in [-1, 0, 1]:
                test = sn + ((pitch // 12) + octave) * 12
                dist = abs(test - pitch)
                if dist < min_dist and 0 <= test <= 127:
                    min_dist = dist
                    best = test
        return best
    
    @classmethod
    def adjust_to_chord(cls, pitch, chord_tones):
        """将音高调整到最近的和弦内音"""
        if (pitch % 12) in chord_tones:
            return pitch
        best = pitch
        min_dist = 12
        for ct in chord_tones:
            for octave in [-1, 0, 1]:
                test = ct + ((pitch // 12) + octave) * 12
                dist = abs(test - pitch)
                if dist < min_dist and 0 <= test <= 127:
                    min_dist = dist
                    best = test
        return best
    
    @classmethod
    def generate_rhythm_pattern(cls, chord_duration, dotted_prob, syncopated_prob, density):
        """
        根据附点概率、切分概率和密度生成节奏模式
        """
        r = random.random()
        if r < dotted_prob:
            if random.random() < 0.5:
                part = chord_duration / 3
                return [part * 2, part]
            else:
                part = chord_duration / 3
                return [part, part * 2]
        elif r < dotted_prob + syncopated_prob:
            if random.random() < 0.5:
                part = chord_duration / 4
                return [part, part * 2, part]
            else:
                part = chord_duration / 4
                return [part * 2, part, part * 2]
        else:
            if density <= 0:
                return []
            notes_per_beat = density * 4
            total_notes = max(1, int(round(chord_duration * notes_per_beat)))
            note_duration = chord_duration / total_notes
            return [note_duration] * total_notes
    
    @classmethod
    def generate_melody_for_chord(cls, chord_duration, chord_tones, scale_notes, 
                                   dotted_prob, syncopated_prob, density, style,
                                   motif_pitches, motif_weight, chromatic_prob,
                                   prev_pitch=None, motif_idx=0):
        """
        根据和弦和节奏参数生成旋律片段，支持变化音概率
        如果density<=0，返回空列表（无旋律）
        """
        if density <= 0:
            return [], prev_pitch, motif_idx
        
        style_params = {
            'classical': {'passing': 0.3, 'neighbor': 0.2, 'leap': 0.1},
            'jazz': {'passing': 0.4, 'neighbor': 0.3, 'leap': 0.2},
            'folk': {'passing': 0.2, 'neighbor': 0.2, 'leap': 0.1}
        }.get(style, {'passing': 0.3, 'neighbor': 0.2, 'leap': 0.1})
        
        rhythm_pattern = cls.generate_rhythm_pattern(chord_duration, dotted_prob, syncopated_prob, density)
        if not rhythm_pattern:
            return [], prev_pitch, motif_idx
        
        notes = []
        current_time = 0.0
        last_pitch = prev_pitch
        all_scale_notes = list(scale_notes)
        all_chord_tones = list(chord_tones)
        all_semitones = list(range(12))
        
        for i, dur in enumerate(rhythm_pattern):
            use_motif = (random.random() < motif_weight) and motif_pitches
            if use_motif:
                motif_pitch = motif_pitches[motif_idx % len(motif_pitches)]
                motif_idx += 1
                pitch_val = cls.adjust_to_chord(motif_pitch, chord_tones)
                pitch_val = cls.adjust_to_scale(pitch_val, scale_notes)
            else:
                # 先判断是否使用变化音
                if random.random() < chromatic_prob:
                    # 从所有半音中排除音阶内音
                    chromatic_choices = [p for p in all_semitones if p not in scale_notes]
                    if chromatic_choices:
                        pitch_class = random.choice(chromatic_choices)
                    else:
                        pitch_class = random.choice(all_scale_notes)
                else:
                    # 正常选音：70%和弦音，30%音阶内非和弦音
                    if random.random() < 0.7:
                        pitch_class = random.choice(all_chord_tones)
                    else:
                        non_chord = [p for p in all_scale_notes if p not in chord_tones]
                        if non_chord:
                            pitch_class = random.choice(non_chord)
                        else:
                            pitch_class = random.choice(all_chord_tones)
                
                # 确定八度
                if last_pitch is not None:
                    best_pitch = None
                    min_dist = 100
                    for octave in range(2, 6):
                        candidate = octave * 12 + pitch_class
                        if 0 <= candidate <= 127:
                            dist = abs(candidate - last_pitch)
                            if dist < min_dist:
                                min_dist = dist
                                best_pitch = candidate
                    pitch_val = best_pitch
                else:
                    pitch_val = 60 + (pitch_class - 60 % 12)
                    if pitch_val < 48:
                        pitch_val += 12
                    elif pitch_val > 84:
                        pitch_val -= 12
            
            n = note.Note()
            n.pitch.midi = pitch_val
            n.quarterLength = dur
            n.offset = current_time
            notes.append(n)
            
            current_time += dur
            last_pitch = pitch_val
        
        return notes, last_pitch, motif_idx

# ==================== 动机发展功能（带左右手） ====================

def get_total_measures(notes):
    """估算总小节数（基于offset）"""
    if not notes:
        return 0
    max_offset = max(n.offset + n.quarterLength for n in notes)
    return int(max_offset // 4) + 1

def get_total_beats(notes):
    """估算总拍数（基于offset）"""
    if not notes:
        return 0
    max_offset = max(n.offset + n.quarterLength for n in notes)
    return max_offset

def extract_motif_by_beats(notes, start_measure, length_beats):
    """
    从音符列表中提取动机，按起始小节和长度（拍）提取
    start_measure: 起始小节数（1-based）
    length_beats: 动机长度（拍）
    """
    start_offset = (start_measure - 1) * 4.0  # 假设4/4拍
    end_offset = start_offset + length_beats
    motif_notes = [copy.deepcopy(n) for n in notes if n.offset >= start_offset and n.offset < end_offset]
    if not motif_notes:
        return None, None
    min_offset = min(n.offset for n in motif_notes)
    for n in motif_notes:
        n.offset -= min_offset
    motif_pitches = [n.pitch.midi for n in motif_notes]
    return motif_notes, motif_pitches

def extract_rhythm_pattern(motif_notes):
    return [n.quarterLength for n in motif_notes]

def apply_development_to_pitches(motif_pitches, technique, scale_notes):
    """对音高序列应用发展手法（倒影、逆行），返回新序列"""
    if technique == "重复":
        return motif_pitches[:]
    elif technique == "倒影":
        if not motif_pitches:
            return []
        axis = motif_pitches[0]
        new_pitches = []
        for p in motif_pitches:
            reflected = axis - (p - axis)
            reflected = MusicTheoryEngine.adjust_to_scale(reflected, scale_notes)
            new_pitches.append(reflected)
        return new_pitches
    elif technique == "逆行":
        return list(reversed(motif_pitches))
    else:
        return motif_pitches[:]

def develop_motif_with_progression_advanced(
    motif_notes, motif_pitches, target_measures, chord_sequence_str,
    chords_per_bar, development_technique, stretch_factor, motif_weight,
    rhythm_source, dotted_prob, syncopated_prob, density, left_style,
    chromatic_prob,
    key='C', mode='major', style='classical', beats_per_measure=4.0
):
    """
    根据和弦进程生成旋律
    如果density<=0，右手不生成任何音符（仅左手伴奏）
    """
    if not motif_notes:
        return stream.Score()
    
    tokens = [s.strip() for s in re.split(r'[,\s]+', chord_sequence_str) if s.strip()]
    if not tokens:
        return stream.Score()
    
    chord_degrees = [MusicTheoryEngine.roman_or_num_to_degree(tok) for tok in tokens]
    
    chord_duration_beats = beats_per_measure / chords_per_bar
    total_chords_needed = int(target_measures * chords_per_bar)
    
    chord_cycle = []
    for i in range(total_chords_needed):
        chord_cycle.append(chord_degrees[i % len(chord_degrees)])
    
    scale_notes = MusicTheoryEngine.get_scale_notes(key, mode)
    developed_pitches = apply_development_to_pitches(motif_pitches, development_technique, scale_notes)
    
    motif_rhythm = extract_rhythm_pattern(motif_notes)
    if stretch_factor != 1.0:
        motif_rhythm = [d * stretch_factor for d in motif_rhythm]
    
    use_motif_rhythm = rhythm_source <= 0.5
    
    right_part = stream.Part()
    right_part.partName = "右手旋律"
    right_part.id = 'right'
    right_part.append(instrument.Piano())
    
    left_part = stream.Part()
    left_part.partName = "左手伴奏"
    left_part.id = 'left'
    left_part.append(instrument.Piano())
    
    current_time = 0.0
    last_pitch = None
    motif_idx = 0
    
    for chord_idx, chord_degree in enumerate(chord_cycle):
        chord_tones = MusicTheoryEngine.get_chord_tones(chord_degree, key, mode)
        
        # 右手旋律生成（仅当密度>0时）
        if density > 0:
            if use_motif_rhythm:
                if motif_notes:
                    total_motif_dur = sum(motif_rhythm)
                    scale = chord_duration_beats / total_motif_dur
                    for n in motif_notes:
                        new_n = copy.deepcopy(n)
                        new_n.offset = current_time + n.offset * scale
                        orig_pitch = n.pitch.midi
                        if (orig_pitch % 12) not in chord_tones:
                            orig_pitch = MusicTheoryEngine.adjust_to_chord(orig_pitch, chord_tones)
                        new_n.pitch.midi = orig_pitch
                        right_part.append(new_n)
            else:
                melody_notes, last_pitch, motif_idx = MusicTheoryEngine.generate_melody_for_chord(
                    chord_duration_beats, chord_tones, scale_notes,
                    dotted_prob, syncopated_prob, density, style,
                    developed_pitches, motif_weight, chromatic_prob,
                    last_pitch, motif_idx
                )
                for n in melody_notes:
                    new_n = copy.deepcopy(n)
                    new_n.offset = current_time + n.offset
                    right_part.append(new_n)
        
        # 左手伴奏生成（根据left_style）
        chord_notes = MusicTheoryEngine.get_chord_notes(chord_degree, key, mode, octave=3)
        root = chord_notes[0]  # 根音
        
        if left_style == "柱形":
            # 两拍模式：第一拍八度根音，第二拍柱形三和弦
            # 将和弦时长平分
            sub_dur = chord_duration_beats / 2
            # 第一拍：八度根音（根音的低八度和高八度，如果可用）
            octave_notes = []
            if root - 12 >= 0:
                octave_notes.append(root - 12)
            if root + 12 <= 127:
                octave_notes.append(root + 12)
            if octave_notes:
                if len(octave_notes) == 1:
                    # 如果只有一个八度音，则作为单音
                    n1 = note.Note()
                    n1.pitch.midi = octave_notes[0]
                    n1.quarterLength = sub_dur
                    n1.offset = current_time
                    n1.volume.velocity = 80
                    left_part.append(n1)
                else:
                    # 两个八度音同时发音
                    chord1 = chord.Chord(octave_notes)
                    chord1.quarterLength = sub_dur
                    chord1.offset = current_time
                    chord1.volume.velocity = 80
                    left_part.append(chord1)
            
            # 第二拍：柱形三和弦
            chord2 = chord.Chord(chord_notes)
            chord2.quarterLength = sub_dur
            chord2.offset = current_time + sub_dur
            chord2.volume.velocity = 69
            left_part.append(chord2)
            
        elif left_style == "分解":
            sub_dur = chord_duration_beats / 3
            for i, p in enumerate(chord_notes):
                n = note.Note()
                n.pitch.midi = p
                n.quarterLength = sub_dur
                n.offset = current_time + i * sub_dur
                n.volume.velocity = 84
                left_part.append(n)
        elif left_style == "琶音":
            sub_dur = chord_duration_beats / 4
            for i, p in enumerate(chord_notes):
                n = note.Note()
                n.pitch.midi = p
                n.quarterLength = sub_dur
                n.offset = current_time + i * sub_dur
                n.volume.velocity = 84
                left_part.append(n)
        
        current_time += chord_duration_beats
    
    score = stream.Score()
    score.append(right_part)
    score.append(left_part)
    return score

# ==================== 辅助函数 ====================

def get_midi_bytes(score):
    temp = tempfile.NamedTemporaryFile(suffix='.mid', delete=False)
    mf = midi.translate.music21ObjectToMidiFile(score)
    mf.open(temp.name, 'wb')
    mf.write()
    mf.close()
    with open(temp.name, 'rb') as f:
        data = f.read()
    import os
    os.unlink(temp.name)
    return data

def get_midi_player_html(midi_bytes, player_id):
    import base64
    midi_base64 = base64.b64encode(midi_bytes).decode('utf-8')
    data_url = f"data:audio/midi;base64,{midi_base64}"
    player_element_id = f"player_{player_id}"
    html = f"""
    <div style="margin:0; padding:0; background:transparent; line-height:0;">
        <script src="https://cdn.jsdelivr.net/combine/npm/tone@14.7.58,npm/@magenta/music@1.23.1/es6/core.js,npm/focus-visible@5,npm/html-midi-player@1.5.0"></script>
        <midi-player
            id="{player_element_id}"
            src="{data_url}"
            sound-font
            style="
                width:100%;
                margin:0;
                padding:0;
                display:block;
                background: transparent;
                border: none;
                box-shadow: none;
                outline: none;
                --midi-player-background: transparent;
                --midi-player-progress-background: transparent;
                --midi-player-button-color: #2d4a1e;
                --midi-player-progress-color: #2d4a1e;
                --midi-player-handle-color: #2d4a1e;
            ">
        </midi-player>
    </div>
    <script>
    (function() {{
        const player = document.getElementById('{player_element_id}');
        if (!player) return;
        player.addEventListener('play', function() {{
            const allPlayers = document.querySelectorAll('midi-player');
            allPlayers.forEach(p => {{
                if (p !== player && p.stop) {{
                    p.stop();
                }}
            }});
        }});
    }})();
    </script>
    """
    return html

# ==================== 侧边栏UI ====================

with st.sidebar:
    st.markdown("### 1. 导入MIDI文件")
    uploaded_files = st.file_uploader("选择MIDI文件", type=['mid','midi'], accept_multiple_files=True)
    raw_melodies = []
    if uploaded_files:
        for f in uploaded_files:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mid') as tmp:
                tmp.write(f.read())
                tmp_path = tmp.name
            try:
                score = converter.parse(tmp_path)
                note_list = list(score.parts[0].flat.getElementsByClass(note.Note))
                if note_list:
                    raw_melodies.append(note_list)
                    st.success(f"已导入: {f.name}")
                else:
                    st.warning(f"无音符: {f.name}")
            except Exception as e:
                st.error(f"解析失败: {f.name} - {str(e)}")
            import os
            os.unlink(tmp_path)

    st.markdown("### 2. 动机发展")
    if raw_melodies:
        total_measures_est = get_total_measures(raw_melodies[0])
        total_beats_est = get_total_beats(raw_melodies[0])
        st.caption(f"当前MIDI估算总小节数: {total_measures_est}, 总拍数: {total_beats_est:.1f}")
        
        key_options = ['C', 'G', 'D', 'A', 'E', 'F', 'Bb', 'Eb', 'Ab']
        selected_key = st.select_slider(
            "调性", options=key_options, value='C',
            help="选择乐曲的主调性，影响旋律的和声色彩"
        )
        
        mode_options = [
            'major', 'minor', 'harmonic_minor', 'melodic_minor', 'dorian', 'mixolydian',
            'major_pentatonic', 'minor_pentatonic',
            'gong (宫)', 'shang (商)', 'jue (角)', 'zhi (徵)', 'yu (羽)'
        ]
        selected_mode_display = st.select_slider(
            "调式", options=mode_options, value='major',
            help="选择调式的类型：西方调式、西方五声调式、中国五声调式（宫商角徵羽）"
        )
        mode_map = {
            'gong (宫)': 'gong', 'shang (商)': 'shang', 'jue (角)': 'jue',
            'zhi (徵)': 'zhi', 'yu (羽)': 'yu'
        }
        selected_mode = mode_map.get(selected_mode_display, selected_mode_display)
        
        style_options = ['classical', 'jazz', 'folk']
        selected_style = st.select_slider(
            "风格", options=style_options, value='classical',
            help="选择音乐风格，影响旋律中的装饰音概率和和声偏好"
        )
        
        # 起始小节（小节）
        start_measure = st.slider(
            "起始小节", min_value=1, max_value=max(1, total_measures_est), value=1,
            help="从第几小节开始提取动机"
        )
        # 动机长度（拍），最大32拍，且不超过文件剩余拍数
        max_motif_beats = min(32, total_beats_est - (start_measure - 1) * 4)
        motif_length_beats = st.slider(
            "动机长度（拍）", min_value=1.0, max_value=max(max_motif_beats, 1.0), value=8.0, step=0.5,
            help="动机的长度，以拍为单位（最大32拍）"
        )
        # 目标乐段长度（小节）
        target_length = st.slider(
            "目标乐段长度（小节）", min_value=1, max_value=64, value=18,
            help="生成乐段的总小节数"
        )
        
        default_prog = "1,5,6,3,4,1,2,5"
        chord_prog_input = st.text_input(
            "和弦进程（罗马数字或阿拉伯数字，逗号或空格分隔）", value=default_prog,
            help="输入和弦序列，例如 1,4,5,1 或 I,IV,V,I"
        )
        
        chords_per_bar = st.select_slider(
            "每小节和弦数", options=[1, 2, 3, 4], value=1,
            help="每小节内更换和弦的次数"
        )
        
        dev_technique = st.select_slider(
            "发展手法", options=["重复", "倒影", "逆行"], value="重复",
            help="对动机音高序列应用的变形手法"
        )
        
        stretch_factor = st.slider(
            "节奏伸缩因子", 0.5, 2.0, 1.0, step=0.1,
            help="控制动机节奏的伸缩比例，0.5=慢一倍，2.0=快一倍"
        )
        
        motif_weight = st.slider(
            "动机保留度 (音高)", 0.0, 1.0, 0.5, step=0.05,
            help="0：完全基于和弦生成音高；1：尽可能使用动机音高并调整到和弦内"
        )
        
        rhythm_source = st.slider(
            "节奏来源", 0.0, 1.0, 0.51, step=0.05,
            help="0=使用动机节奏型；1=使用自由节奏（类型由下方附点和切分倾向决定）"
        )
        
        dotted_prob = st.slider(
            "附点倾向", 0.0, 1.0, 0.33, step=0.05,
            disabled=rhythm_source <= 0.5,
            help="附点节奏的出现概率"
        )
        syncopated_prob = st.slider(
            "切分倾向", 0.0, 1.0, 0.33, step=0.05,
            disabled=rhythm_source <= 0.5,
            help="切分节奏的出现概率。剩余概率为均分节奏。"
        )
        
        density = st.slider(
            "音符密度", 0.0, 1.0, 0.5, step=0.05,
            help="0=无旋律音符（全休止），1=每拍4个音符（均分时）。"
        )
        
        chromatic_prob = st.slider(
            "变化音概率", 0.0, 1.0, 0.0, step=0.05,
            disabled=rhythm_source <= 0.5,
            help="旋律中出现调式外半音的概率。0=全为调内音，1=完全随机半音。"
        )
        
        left_style = st.select_slider(
            "左手演奏法", options=["柱形", "分解", "琶音"], value="柱形",
            help="柱形：第一拍八度根音（力度80），第二拍柱形三和弦（力度69）；分解：三连音分解；琶音：四连音快速分解"
        )
        
        if st.button("生成带伴奏的乐段"):
            if not raw_melodies:
                st.warning("请先导入MIDI")
            else:
                source_notes = raw_melodies[0]
                motif_notes, motif_pitches = extract_motif_by_beats(
                    source_notes, start_measure, motif_length_beats
                )
                if not motif_notes:
                    st.error("指定小节和拍数内无音符，请调整范围")
                else:
                    developed_score = develop_motif_with_progression_advanced(
                        motif_notes, motif_pitches, target_length, chord_prog_input,
                        chords_per_bar, dev_technique, stretch_factor, motif_weight,
                        rhythm_source, dotted_prob, syncopated_prob, density, left_style,
                        chromatic_prob,
                        key=selected_key, mode=selected_mode, style=selected_style, beats_per_measure=4.0
                    )
                    # 插入到最前面
                    st.session_state.variants.insert(0, developed_score)
                    st.session_state.variant_meta.insert(0, {
                        'type': 'development_advanced',
                        'start_measure': start_measure,
                        'motif_length_beats': motif_length_beats,
                        'target_length': target_length,
                        'chord_prog': chord_prog_input,
                        'chords_per_bar': chords_per_bar,
                        'technique': dev_technique,
                        'stretch': stretch_factor,
                        'motif_weight': motif_weight,
                        'rhythm_source': rhythm_source,
                        'dotted_prob': dotted_prob,
                        'syncopated_prob': syncopated_prob,
                        'density': density,
                        'chromatic_prob': chromatic_prob,
                        'left_style': left_style,
                        'key': selected_key,
                        'mode': selected_mode_display,
                        'style': selected_style
                    })
                    st.session_state.labels_surprise.insert(0, None)
                    st.session_state.labels_beauty.insert(0, None)
                    st.session_state.labels_feelings.insert(0, "")
                    st.session_state.save_indicator.insert(0, "")
                    st.success(f"已生成带伴奏的乐段，作为变体 #0 添加")
    else:
        st.info("请先导入MIDI文件")

# ==================== 主界面 ====================

if st.session_state.variants:
    for idx, var in enumerate(st.session_state.variants[:10]):
        indicator = st.session_state.save_indicator[idx] if idx < len(st.session_state.save_indicator) else ""
        meta = st.session_state.variant_meta[idx] if idx < len(st.session_state.variant_meta) else {}
        
        if meta:
            param_str = (f"动机发展: {meta.get('start_measure')}小节起{meta.get('motif_length_beats',0):.1f}拍 → {meta.get('target_length')}小节 | "
                         f"调性:{meta.get('key','C')} {meta.get('mode','major')} {meta.get('style','classical')} | "
                         f"和弦:{meta.get('chord_prog')} | 密度:{meta.get('chords_per_bar')}/小节 | "
                         f"手法:{meta.get('technique')} | 伸缩:{meta.get('stretch')} | "
                         f"动机保留:{meta.get('motif_weight',0.5):.2f} | "
                         f"节奏来源:{'动机' if meta.get('rhythm_source',0)<=0.5 else '自由'} | "
                         f"附点:{meta.get('dotted_prob',0.33):.2f} | "
                         f"切分:{meta.get('syncopated_prob',0.33):.2f} | "
                         f"密度:{meta.get('density',0.5):.2f} | "
                         f"变化音:{meta.get('chromatic_prob',0.0):.2f} | "
                         f"左手:{meta.get('left_style','柱形')}")
        else:
            param_str = "变体"
        
        expander_title = f"变体 #{idx} {indicator}  {param_str}"
        
        with st.expander(expander_title, expanded=True):
            left_col, right_col = st.columns(2)
            with left_col:
                midi_bytes = get_midi_bytes(var)
                player_html = get_midi_player_html(midi_bytes, idx)
                st.components.v1.html(player_html, height=60)

                if idx < len(st.session_state.labels_feelings):
                    current_f = st.session_state.labels_feelings[idx] if st.session_state.labels_feelings[idx] is not None else ""
                else:
                    current_f = ""
                st.text_area(
                    "感受词",
                    value=current_f,
                    height=80,
                    placeholder="请标注变体听感（例如：跳跃、不协和、温柔...）",
                    key=f"f_{idx}",
                    label_visibility="collapsed"
                )

                st.markdown('<div class="button-row">', unsafe_allow_html=True)
                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    st.download_button(
                        "⬇️ 下载MIDI文件",
                        data=get_midi_bytes(var),
                        file_name=f"variant_{idx}.mid",
                        mime="audio/midi",
                        key=f"download_{idx}"
                    )
                with btn_col2:
                    if st.button("💾 保存标注", key=f"save_left_{idx}"):
                        current_s = st.session_state.get(f"s_{idx}", 0.5)
                        current_b = st.session_state.get(f"b_{idx}", 0.5)
                        current_f = st.session_state.get(f"f_{idx}", "")

                        while len(st.session_state.labels_surprise) <= idx:
                            st.session_state.labels_surprise.append(None)
                        while len(st.session_state.labels_beauty) <= idx:
                            st.session_state.labels_beauty.append(None)
                        while len(st.session_state.labels_feelings) <= idx:
                            st.session_state.labels_feelings.append("")
                        while len(st.session_state.save_indicator) <= idx:
                            st.session_state.save_indicator.append("")

                        st.session_state.labels_surprise[idx] = current_s
                        st.session_state.labels_beauty[idx] = current_b
                        st.session_state.labels_feelings[idx] = current_f
                        st.session_state.save_indicator[idx] = "✅"
                        st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

            with right_col:
                if idx < len(st.session_state.labels_surprise):
                    current_s = st.session_state.labels_surprise[idx] if st.session_state.labels_surprise[idx] is not None else 0.5
                else:
                    current_s = 0.5
                if idx < len(st.session_state.labels_beauty):
                    current_b = st.session_state.labels_beauty[idx] if st.session_state.labels_beauty[idx] is not None else 0.5
                else:
                    current_b = 0.5
                new_s = st.slider("意外度评分", 0.0, 1.0, current_s, key=f"s_{idx}")
                new_b = st.slider("好听度评分", 0.0, 1.0, current_b, key=f"b_{idx}")
else:
    st.info("请在左侧上传MIDI文件，并在动机发展中生成带伴奏的乐段")
