import React from 'react';
import {Composition} from 'remotion';
import {Overview, TOTAL} from './Overview';

export const Root: React.FC = () => (
  <Composition id="Overview" component={Overview} durationInFrames={TOTAL} fps={30} width={1920} height={1080} />
);
