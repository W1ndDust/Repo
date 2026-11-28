"""按需重写 deb 的 control 字段（只重打 control.tar，data.tar 逐字节保留）。"""
import io, sys, tarfile, hashlib
from pathlib import Path


def split_ar(raw: bytes):
    assert raw[:8] == b"!<arch>\n", "不是 ar 归档"
    out, off = [], 8
    while off < len(raw):
        h = raw[off:off + 60]
        size = int(h[48:58])
        out.append([h, raw[off + 60:off + 60 + size]])
        off += 60 + size + size % 2
    return out


def rewrite(src: Path, dst: Path, fields: dict):
    members = split_ar(src.read_bytes())
    out = bytearray(b"!<arch>\n")
    for h, body in members:
        name = h[:16].decode().strip().rstrip("/")
        if name.startswith("control.tar"):
            mode = "w:xz" if name.endswith(".xz") else "w:gz" if name.endswith(".gz") else "w"
            src_tar = tarfile.open(fileobj=io.BytesIO(body), mode="r:*")
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode=mode) as dst_tar:
                for item in src_tar:
                    data = src_tar.extractfile(item).read() if item.isfile() else None
                    if item.name.lstrip("./") == "control":
                        lines = data.decode().splitlines()
                        seen = set()
                        new = []
                        for line in lines:
                            key = line.split(":", 1)[0] if ":" in line and not line[0].isspace() else None
                            if key in fields:
                                new.append(f"{key}: {fields[key]}")
                                seen.add(key)
                            else:
                                new.append(line)
                        for k, v in fields.items():
                            if k not in seen:
                                new.append(f"{k}: {v}")
                        data = ("\n".join(new) + "\n").encode()
                        item.size = len(data)
                    dst_tar.addfile(item, io.BytesIO(data) if data is not None else None)
            body = buf.getvalue()
            h = h[:48] + str(len(body)).encode().ljust(10) + h[58:]
        out += h + body
        if len(body) % 2:
            out += b"\n"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(out)
    return hashlib.sha256(bytes(out)).hexdigest()


if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    fields = dict(pair.split("=", 1) for pair in sys.argv[3:])
    print(rewrite(src, dst, fields))
