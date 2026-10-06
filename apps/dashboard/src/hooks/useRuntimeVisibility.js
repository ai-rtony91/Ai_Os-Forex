import { useEffect, useMemo, useState } from 'react';
import {
  createRuntimeVisibilityErrorState,
  fetchRuntimeVisibilityReadOnly,
  RUNTIME_VISIBILITY_STATES,
} from '../runtimeVisibilityClient.js';
import { mapRuntimeVisibilityDisplayModel } from '../runtimeVisibilityAdapter.js';

const INITIAL_STATE = Object.freeze({
  sourceLabel: 'UNKNOWN',
  runtimeState: RUNTIME_VISIBILITY_STATES.UNAVAILABLE,
  loading: true,
  data: null,
  error: null,
});

export default function useRuntimeVisibility(config) {
  const [state, setState] = useState(INITIAL_STATE);

  useEffect(() => {
    let active = true;
    queueMicrotask(() => { if (active) setState((current) => ({ ...current, loading: true })); });

    fetchRuntimeVisibilityReadOnly(config)
      .then((result) => { if (active) setState(result); })
      .catch((error) => { if (active) setState(createRuntimeVisibilityErrorState(error)); });

    return () => { active = false; };
  }, [config]);

  const displayModel = useMemo(() => (
    state.data
      ? mapRuntimeVisibilityDisplayModel(state.data, { sourceLabel: state.sourceLabel })
      : null
  ), [state.data, state.sourceLabel]);

  return { ...state, displayModel };
}
