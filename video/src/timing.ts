import type React from 'react';

export const FPS = 30;

export type SceneMeta = {
  key: string;
  chapter: string;
  nav: string;
  duration: number;
};

/** 场景时长表（帧）。调整这里即可改变各章停留时间与总片长。 */
export const SCENES: SceneMeta[] = [
  { key: 'title', chapter: '00', nav: '开场', duration: 150 },
  { key: 'why', chapter: '01', nav: '为什么要做', duration: 480 },
  { key: 'solves', chapter: '02', nav: '能解决什么', duration: 570 },
  { key: 'notSolves', chapter: '03', nav: '不能解决什么', duration: 450 },
  { key: 'notFull', chapter: '04', nav: '为什么不做全量', duration: 470 },
  { key: 'roadmap', chapter: '05', nav: '之后的打算', duration: 480 },
  { key: 'collab', chapter: '06', nav: '如何协作', duration: 660 },
  { key: 'deliverables', chapter: '07', nav: '交付成果', duration: 450 },
  { key: 'closing', chapter: '08', nav: '收尾', duration: 180 },
];

export const OFFSETS: number[] = (() => {
  const offsets: number[] = [];
  let cursor = 0;
  for (const s of SCENES) {
    offsets.push(cursor);
    cursor += s.duration;
  }
  return offsets;
})();

export const TOTAL_DURATION = SCENES.reduce((acc, s) => acc + s.duration, 0);

export type SceneComponent = React.FC;
