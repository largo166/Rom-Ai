import { useState, useRef, useCallback } from 'react';
import { Upload, FileAudio, Loader2, Mic } from 'lucide-react';
import { uploadMeetingAudio, transcribeMeetingAudio } from '../../lib/projectsApi';

type Props = {
  projectId: string;
  meetingId: string;
  onTranscribed?: (transcript: string) => void;
};

const ACCEPTED_FORMATS = '.wav,.mp3,.m4a,.ogg,.flac,.webm';

export function AudioUploader({ projectId, meetingId, onTranscribed }: Props) {
  const [uploading, setUploading] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [audioUploaded, setAudioUploaded] = useState(false);
  const [fileName, setFileName] = useState('');
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    async (file: File) => {
      setError('');
      setUploading(true);
      setFileName(file.name);
      try {
        await uploadMeetingAudio(projectId, meetingId, file);
        setAudioUploaded(true);
      } catch (err) {
        setError(String(err));
        setFileName('');
      } finally {
        setUploading(false);
      }
    },
    [projectId, meetingId],
  );

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      const file = e.dataTransfer.files?.[0];
      if (file) handleFile(file);
    },
    [handleFile],
  );

  const handleTranscribe = async () => {
    setError('');
    setTranscribing(true);
    try {
      const data = await transcribeMeetingAudio(projectId, meetingId);
      onTranscribed?.(data.transcript);
    } catch (err) {
      setError(`转写失败：${String(err)}`);
    } finally {
      setTranscribing(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* 拖拽上传区 */}
      <div
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
        onClick={() => inputRef.current?.click()}
        className="cursor-pointer rounded-lg border-2 border-dashed border-stone-300 bg-stone-50 p-8 text-center transition-colors hover:border-[#C2703A] hover:bg-[#C2703A]/5"
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_FORMATS}
          onChange={handleInputChange}
          className="hidden"
        />
        <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-stone-100 text-stone-400">
          {fileName ? <FileAudio size={24} className="text-[#C2703A]" /> : <Upload size={24} />}
        </div>
        <p className="text-sm text-stone-600">
          {fileName ? fileName : '拖拽音频文件到此处，或点击选择'}
        </p>
        <p className="mt-1 text-xs text-stone-400">
          支持 WAV / MP3 / M4A / OGG / FLAC / WebM，最大 100MB
        </p>
      </div>

      {/* 上传进度 */}
      {uploading && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs text-stone-500">
            <Loader2 size={12} className="animate-spin" />
            正在上传音频…
          </div>
          <div className="h-1.5 rounded-full bg-stone-200">
            <div className="h-1.5 w-2/3 animate-pulse rounded-full bg-[#C2703A]" />
          </div>
        </div>
      )}

      {/* 转写按钮 */}
      {audioUploaded && !transcribing && (
        <button
          onClick={handleTranscribe}
          className="inline-flex items-center gap-2 rounded-md bg-[#C2703A] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#A85C30]"
        >
          <Mic size={14} />
          开始转写
        </button>
      )}

      {transcribing && (
        <div className="flex items-center gap-2 text-sm text-stone-500">
          <Loader2 size={14} className="animate-spin text-[#C2703A]" />
          <span className="animate-pulse">正在转写中，请稍候…</span>
        </div>
      )}

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {error}
        </div>
      )}
    </div>
  );
}
