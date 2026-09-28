import React from 'react';
import {AbsoluteFill, Sequence} from 'remotion';
import {Background} from './components/Background';
import {ProgressOverlay} from './components/ProgressOverlay';
import {SceneWrap} from './components/SceneShell';
import {OFFSETS, SCENES} from './timing';
import {SceneTitle} from './scenes/SceneTitle';
import {SceneWhy} from './scenes/SceneWhy';
import {SceneSolves} from './scenes/SceneSolves';
import {SceneNotSolves} from './scenes/SceneNotSolves';
import {SceneNotFull} from './scenes/SceneNotFull';
import {SceneRoadmap} from './scenes/SceneRoadmap';
import {SceneCollab} from './scenes/SceneCollab';
import {SceneDeliverables} from './scenes/SceneDeliverables';
import {SceneClosing} from './scenes/SceneClosing';

const COMPONENTS: Record<string, React.FC> = {
  title: SceneTitle,
  why: SceneWhy,
  solves: SceneSolves,
  notSolves: SceneNotSolves,
  notFull: SceneNotFull,
  roadmap: SceneRoadmap,
  collab: SceneCollab,
  deliverables: SceneDeliverables,
  closing: SceneClosing,
};

export const Main: React.FC = () => {
  return (
    <AbsoluteFill>
      <Background />
      {SCENES.map((s, i) => {
        const Comp = COMPONENTS[s.key];
        return (
          <Sequence
            key={s.key}
            name={`${s.chapter} ${s.nav}`}
            from={OFFSETS[i]}
            durationInFrames={s.duration}
          >
            <SceneWrap duration={s.duration}>
              <Comp />
            </SceneWrap>
          </Sequence>
        );
      })}
      <ProgressOverlay />
    </AbsoluteFill>
  );
};
