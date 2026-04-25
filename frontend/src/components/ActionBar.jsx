export default function ActionBar({ onMaskAll, onDownload, downloading, allMasked }) {
  return (
    <div className="action-bar">
      <button type="button" className="secondary-button" onClick={onMaskAll}>
        {allMasked ? 'Unmask All' : 'Mask All'}
      </button>
      <button type="button" className="primary-button" onClick={onDownload} disabled={downloading}>
        {downloading ? 'Preparing Safe Copy...' : 'Download Safe Copy'}
      </button>
    </div>
  )
}
