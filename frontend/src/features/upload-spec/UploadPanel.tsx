import { ChangeEvent, DragEvent, FormEvent, useRef, useState } from "react";

interface UploadPanelProps {
  onUpload: (file: File) => Promise<void> | void;
  isUploading: boolean;
  disabled?: boolean;
  error: string | null;
}

const MAX_FILE_SIZE = 16 * 1024 * 1024;
const ACCEPTED_EXTENSIONS = new Set(["docx", "pdf"]);

function formatFileSize(size: number) {
  if (size < 1024 * 1024) {
    return `${Math.round(size / 1024)} KB`;
  }

  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function UploadPanel({
  onUpload,
  isUploading,
  disabled = false,
  error
}: UploadPanelProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [isDragActive, setIsDragActive] = useState(false);

  function validateFile(file: File) {
    const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
    if (!ACCEPTED_EXTENSIONS.has(extension)) {
      return "Use a .docx or .pdf file.";
    }

    if (file.size > MAX_FILE_SIZE) {
      return "The file is larger than 16 MB.";
    }

    return null;
  }

  function clearSelection() {
    setSelectedFile(null);
    setValidationError(null);

    if (inputRef.current) {
      inputRef.current.value = "";
    }
  }

  function handleSelectedFile(file: File | null) {
    if (!file) {
      clearSelection();
      return;
    }

    const nextError = validateFile(file);
    setValidationError(nextError);
    setSelectedFile(nextError ? null : file);
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    handleSelectedFile(event.target.files?.[0] ?? null);
  }

  function handleDragOver(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    if (disabled || isUploading) {
      return;
    }
    setIsDragActive(true);
  }

  function handleDragLeave(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDragActive(false);
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDragActive(false);

    if (disabled || isUploading) {
      return;
    }

    handleSelectedFile(event.dataTransfer.files?.[0] ?? null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFile || disabled) {
      return;
    }

    await onUpload(selectedFile);
  }

  return (
    <div className="panel">
      <div className="section-heading">
        <h2>Upload a specification</h2>
        <p>Start the analysis against the new API surface and keep the task resumable via URL.</p>
      </div>
      <form onSubmit={handleSubmit} className="stack">
        <label
          className={`upload-dropzone${isDragActive ? " upload-dropzone-active" : ""}${
            selectedFile ? " upload-dropzone-ready" : ""
          }`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <span className="upload-title">
            {selectedFile ? "Replace the current file" : "Choose a Word or PDF file"}
          </span>
          <span className="upload-hint">
            Formats: .docx, .pdf, max 16 MB. Drag and drop is supported too.
          </span>
          <input
            ref={inputRef}
            type="file"
            accept=".docx,.pdf"
            onChange={handleFileChange}
            disabled={disabled || isUploading}
          />
        </label>
        {selectedFile ? (
          <div className="selected-file-card">
            <div>
              <strong>{selectedFile.name}</strong>
              <p className="muted-copy">{formatFileSize(selectedFile.size)}</p>
            </div>
            <button
              type="button"
              className="secondary-button"
              onClick={clearSelection}
              disabled={disabled || isUploading}
            >
              Remove
            </button>
          </div>
        ) : null}
        {validationError ? <p className="error-banner">{validationError}</p> : null}
        {error ? <p className="error-banner">{error}</p> : null}
        <button
          type="submit"
          className="primary-button"
          disabled={!selectedFile || isUploading || disabled}
        >
          {isUploading ? "Uploading..." : "Run analysis"}
        </button>
      </form>
    </div>
  );
}
