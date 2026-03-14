import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { UploadPanel } from "@/features/upload-spec/UploadPanel";

describe("UploadPanel", () => {
  it("uploads a valid document through the standalone form", async () => {
    const user = userEvent.setup();
    const onUpload = vi.fn().mockResolvedValue(undefined);

    render(<UploadPanel onUpload={onUpload} isUploading={false} error={null} />);

    const input = screen.getByLabelText(/choose a word or pdf file/i);
    const file = new File(["spec"], "specification.pdf", {
      type: "application/pdf"
    });

    await user.upload(input, file);

    expect(screen.getByText("specification.pdf")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /run analysis/i }));

    expect(onUpload).toHaveBeenCalledTimes(1);
    expect(onUpload).toHaveBeenCalledWith(file);
  });

  it("shows a validation error for unsupported file extensions", async () => {
    render(<UploadPanel onUpload={vi.fn()} isUploading={false} error={null} />);

    const input = screen.getByLabelText(/choose a word or pdf file/i);
    const file = new File(["plain text"], "notes.txt", {
      type: "text/plain"
    });

    fireEvent.change(input, {
      target: {
        files: [file]
      }
    });

    expect(screen.getByText(/use a \.docx or \.pdf file/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run analysis/i })).toBeDisabled();
  });
});
