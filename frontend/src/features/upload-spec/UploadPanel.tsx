import { ChangeEvent, FormEvent, useState } from "react";

interface UploadPanelProps {
  onUpload: (file: File) => Promise<void> | void;
  isUploading: boolean;
  disabled?: boolean;
  error: string | null;
}

const MAX_FILE_SIZE = 16 * 1024 * 1024;
const ACCEPTED_EXTENSIONS = new Set(["docx", "pdf"]);

export function UploadPanel({
  onUpload,
  isUploading,
  disabled = false,
  error
}: UploadPanelProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

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

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    if (!file) {
      setSelectedFile(null);
      setValidationError(null);
      return;
    }

    const nextError = validateFile(file);
    setValidationError(nextError);
    setSelectedFile(nextError ? null : file);
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
        <p>Start the analysis against the new API surface.</p>
      </div>
      <form onSubmit={handleSubmit} className="stack">
        <label className="upload-dropzone">
          <span className="upload-title">
            {selectedFile ? selectedFile.name : "Choose a Word or PDF file"}
          </span>
          <span className="upload-hint">Formats: .docx, .pdf, max 16 MB</span>
          <input
            type="file"
            accept=".docx,.pdf"
            onChange={handleFileChange}
            disabled={disabled || isUploading}
          />
        </label>
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
