import { ChangeEvent, DragEvent, FormEvent, useRef, useState } from "react";
import { FileText, UploadCloud } from "lucide-react";

import { formatFileSize } from "@/shared/lib/locale";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card";

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
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [isDragActive, setIsDragActive] = useState(false);

  function validateFile(file: File) {
    const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
    if (!ACCEPTED_EXTENSIONS.has(extension)) {
      return "Поддерживаются только файлы .docx и .pdf.";
    }

    if (file.size > MAX_FILE_SIZE) {
      return "Файл превышает лимит 16 МБ.";
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
    <Card className="border-border/70 bg-card/85">
      <CardHeader>
        <CardTitle className="text-2xl">Загрузка спецификации</CardTitle>
        <CardDescription>
          Загрузите исходный документ, запустите анализ и при необходимости продолжите его по ссылке.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <label
            className={[
              "group grid gap-3 rounded-[calc(var(--radius)+2px)] border border-dashed px-5 py-6 transition-[border-color,background-color,transform] hover:-translate-y-0.5",
              "border-primary/30 bg-background/60 hover:border-primary/50 hover:bg-background/80",
              isDragActive ? "border-primary/70 bg-primary/10" : "",
              selectedFile ? "border-solid border-primary/50 bg-background/85" : ""
            ].join(" ")}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            <div className="flex items-start gap-3">
              <div className="rounded-xl border border-primary/20 bg-primary/10 p-2 text-primary">
                <UploadCloud className="size-4" />
              </div>
              <div className="space-y-1">
                <span className="block text-sm font-semibold text-foreground">
                  {selectedFile ? "Заменить выбранный файл" : "Выберите файл Word или PDF"}
                </span>
                <span className="block text-sm leading-6 text-muted-foreground">
                  Форматы: `.docx`, `.pdf`, максимум 16 МБ. Можно перетащить файл прямо сюда.
                </span>
              </div>
            </div>
            <input
              ref={inputRef}
              type="file"
              accept=".docx,.pdf"
              onChange={handleFileChange}
              disabled={disabled || isUploading}
              className="text-sm text-muted-foreground file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-2 file:text-xs file:font-semibold file:text-primary-foreground"
            />
          </label>
          {selectedFile ? (
            <div className="flex flex-col gap-3 rounded-xl border border-border/80 bg-muted/50 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-start gap-3">
                <div className="rounded-lg border border-border/70 bg-background/70 p-2 text-primary">
                  <FileText className="size-4" />
                </div>
                <div className="space-y-1">
                  <strong>{selectedFile.name}</strong>
                  <p className="text-sm text-muted-foreground">{formatFileSize(selectedFile.size)}</p>
                </div>
              </div>
              <Button
                type="button"
                variant="secondary"
                onClick={clearSelection}
                disabled={disabled || isUploading}
              >
                Убрать
              </Button>
            </div>
          ) : null}
          {validationError ? (
            <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive-foreground">
              {validationError}
            </div>
          ) : null}
          {error ? (
            <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive-foreground">
              {error}
            </div>
          ) : null}
          <Button type="submit" className="w-full sm:w-auto" disabled={!selectedFile || isUploading || disabled}>
            {isUploading ? "Загружаем..." : "Запустить анализ"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
