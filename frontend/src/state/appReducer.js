export const initialState = {
  phase: 'upload',
  file: null,
  scanResult: null,
  maskedIds: new Set(),
  mockMode: false,
  slowWarning: false,
  error: null,
}

export function appReducer(state, action) {
  switch (action.type) {
    case 'START_SCAN':
      return {
        ...state,
        phase: 'scanning',
        file: action.file,
        scanResult: null,
        maskedIds: new Set(),
        slowWarning: false,
        error: null,
      }
    case 'SCAN_SUCCESS':
      return {
        ...state,
        phase: 'review',
        scanResult: action.result,
        slowWarning: false,
        error: null,
      }
    case 'SCAN_SLOW':
      if (state.mockMode || state.phase !== 'scanning') {
        return state
      }
      return {
        ...state,
        slowWarning: true,
      }
    case 'SCAN_ERROR':
      return {
        ...state,
        phase: 'upload',
        file: null,
        scanResult: null,
        maskedIds: new Set(),
        slowWarning: false,
        error: action.error,
      }
    case 'TOGGLE_MASK': {
      const next = new Set(state.maskedIds)
      if (next.has(action.findingId)) {
        next.delete(action.findingId)
      } else {
        next.add(action.findingId)
      }
      return {
        ...state,
        maskedIds: next,
      }
    }
    case 'MASK_ALL':
      return {
        ...state,
        maskedIds: new Set((state.scanResult?.findings ?? []).map((finding) => finding.id)),
      }
    case 'UNMASK_ALL':
      return {
        ...state,
        maskedIds: new Set(),
      }
    case 'START_DOWNLOAD':
      return {
        ...state,
        phase: 'downloading',
        error: null,
      }
    case 'DOWNLOAD_DONE':
      return {
        ...state,
        phase: 'complete',
        slowWarning: false,
      }
    case 'RESET':
      return {
        ...initialState,
        mockMode: state.mockMode,
      }
    case 'SET_MOCK':
      return {
        ...state,
        mockMode: action.enabled,
      }
    default:
      return state
  }
}
