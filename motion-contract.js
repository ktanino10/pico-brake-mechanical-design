export const DURATION = 40;
export const GAP_MM = 0.2;
export const VIEWS = ['model', 'section', 'schematic', 'three'];

const smooth = value => {
  const u = Math.min(1, Math.max(0, value));
  return u * u * (3 - 2 * u);
};

export function motionRole(part) {
  const id = part.id;
  if (id === 'ARMATURE' || /^(SPRING_CLAMP_TIP_|SPRING_TIP_BOLT_|SPRING_TIP_NUT_PLATE_)/.test(id)) return 'axial';
  if (/^SPRING_\d+$/.test(id)) return 'spring';
  if (['coil', 'support', 'wiring'].includes(part.group) ||
      /^(FRAME_BOLT_|STATOR_BOLT_|CAP_BOLT_|RETAINER_BOLT_|STRAIN_BOLT_|MOTOR_INTERFACE_BOLT_|BEARING_BALL_)/.test(id) ||
      ['REF_FRAME', 'REF_MOTOR_ENVELOPE'].includes(id)) return 'fixed';
  if (part.group === 'rotor' || /^(RIM_BOLT_|WHEEL_BOLT_|HUB_CONNECT_BOLT_|SPRING_ROOT_BOLT_|RELEASE_STOP_)/.test(id) ||
      ['REF_WHEEL', 'REF_SHAFT'].includes(id)) return 'rotating';
  throw new Error(`動作グループが定義されていません: ${id}`);
}

export function springWeight(x, y, index) {
  const angle = index * 2 * Math.PI / 3;
  return smooth((-x * Math.sin(angle) + y * Math.cos(angle) - 6) / 24);
}

function stageAt(t) {
  if (t < 4) return ['回転前', '動作を再生するか、接触前・接触・停止の場面を選べます。'];
  if (t < 11) return ['1 回る', '白い印のあるホイールと薄い円盤が一緒に回ります。灰色と橙色の部品は固定です。'];
  if (t < 17) return ['駆動OFF・惰性回転', '駆動を止めても、すぐには止まりません。まだ摩擦面には接触していません。'];
  if (t < 22) return ['2 電磁石が引く', 'ハブの軸位置を保ち、薄い円盤だけが固定摩擦面へ近づきます。'];
  if (t < 29) return ['3 接触して減速', '止めるのは固定摩擦面との摩擦です。反力は固定部を通して機体へ伝わります。'];
  if (t < 32) return ['停止・接触維持', '回転は停止。外力がなければ一定の保持トルクが出続けるとは限りません。'];
  if (t < 35.5) return ['コイルOFF・ばねで解除', '接線板ばねの根元はハブ側に残り、円盤が離れます。'];
  return ['解除後も停止', 'すき間が戻りました。自動では再始動しない説明です。'];
}

let angle = 20;
const samples = Array.from({length: 961}, (_, i) => {
  const t = Math.min(i / 24, 40);
  let speed = 0;
  if (t >= 4 && t < 11) speed = 76 * smooth((t - 4) / 0.8);
  else if (t >= 11 && t < 22) speed = 76 - 6 * Math.min(1, (t - 11) / 3);
  else if (t >= 22 && t < 29) speed = 70 * (1 - smooth((t - 22) / 7));
  angle += speed / 24;
  let travel = GAP_MM * smooth((t - 18) / 4);
  if (t >= 32.5) travel = GAP_MM * (1 - smooth((t - 32.5) / 3));
  return {angle, travel, speed};
});

export function poseAt(time) {
  if (!Number.isFinite(time) || time < 0 || time > DURATION) throw new Error('動作時刻が範囲外です。');
  const index = Math.min(959, Math.floor(time * 24));
  const u = Math.min(1, time * 24 - index);
  const a = samples[index], b = samples[index + 1];
  const [stage, explanation] = stageAt(time);
  return {
    time, stage, explanation,
    angle: a.angle + (b.angle - a.angle) * u,
    travel: a.travel + (b.travel - a.travel) * u,
    speed: a.speed + (b.speed - a.speed) * u,
    drive: time >= 4 && time < 11,
    coil: time >= 17 && time < 32,
    contact: time >= 22 && time <= 32.5,
    braking: time >= 22 && time < 29,
  };
}

export function initialMotionState() {
  return {view: 'model', time: 4, playing: false, explode: 0, cutaway: true, notice: ''};
}

function range(value, min, max, name) {
  if (!Number.isFinite(value) || value < min || value > max) throw new Error(`${name}が範囲外です。`);
}

export function transition(state, action) {
  const next = {...state, notice: ''};
  switch (action.type) {
    case 'play':
      if (state.explode > 0) {
        next.notice = '分解表示中は動作を再生できません。組み戻してください。';
        next.playing = false;
      } else {
        if (state.time >= DURATION) next.time = 4;
        next.playing = !state.playing;
      }
      break;
    case 'pause':
      next.playing = false;
      break;
    case 'reset':
      return {...initialMotionState(), view: state.view};
    case 'seek':
      range(action.time, 0, DURATION, '時刻');
      next.time = action.time;
      next.playing = false;
      if (state.explode > 0) {
        next.explode = 0;
        next.notice = '組み戻して選んだ時点へ移動しました。再生は停止しています。';
      }
      if (action.view) {
        if (!VIEWS.includes(action.view)) throw new Error('表示の種類が不正です。');
        next.view = action.view;
      }
      break;
    case 'tick':
      range(action.delta, 0, 0.25, '経過時間');
      if (state.playing && state.explode === 0) {
        next.time = Math.min(DURATION, state.time + action.delta);
        if (next.time === DURATION) next.playing = false;
      }
      break;
    case 'explode':
      range(action.value, 0, 100, '分解量');
      next.explode = action.value;
      next.playing = false;
      if (action.value > 0) {
        next.time = 4;
        if (!['model', 'three'].includes(state.view)) next.view = 'model';
        next.notice = '分解は作動状態ではありません。動作をリセットして停止しました。';
      } else {
        next.notice = '組み戻しました。動作は停止したままです。';
      }
      break;
    case 'view':
      if (!VIEWS.includes(action.value)) throw new Error('表示の種類が不正です。');
      next.view = action.value;
      if (state.explode > 0 && ['section', 'schematic'].includes(action.value)) {
        next.explode = 0;
        next.playing = false;
        next.notice = '断面を見るため組み戻しました。動作は停止しています。';
      }
      break;
    case 'cutaway':
      if (typeof action.value !== 'boolean') throw new Error('内部表示の指定が不正です。');
      next.cutaway = action.value;
      break;
    default:
      throw new Error('未定義の操作です。');
  }
  return next;
}
