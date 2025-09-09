```py

import numpy as np
import scipy.io.wavfile as wavfile
import argparse
import os

# --- MFSK Configuration ---
# Using 16 frequencies to represent 4 bits per symbol (2^4 = 16)
# This significantly increases data density.
SAMPLE_RATE = 44100  # Hz
SYMBOL_DURATION = 0.03  # Duration of each symbol tone in seconds. SHORTER = FASTER.
AMPLITUDE = 32767 // 4 # Max amplitude for 16-bit audio, reduced to avoid clipping

# Frequencies for MFSK. Spaced to be distinguishable by FFT.
BASE_FREQUENCY = 1000 # Hz
FREQUENCY_STEP = 150  # Hz
NUM_FREQUENCIES = 16
FREQUENCIES = np.arange(NUM_FREQUENCIES) * FREQUENCY_STEP + BASE_FREQUENCY

# Sync header remains the same, but can be shorter as detection is robust
SYNC_HEADER_FREQ = 5000 # A distinct frequency outside the data range
SYNC_HEADER_DURATION = 0.3 # s

SAMPLES_PER_SYMBOL = int(SAMPLE_RATE * SYMBOL_DURATION)
SAMPLES_PER_SYNC_HEADER = int(SAMPLE_RATE * SYNC_HEADER_DURATION)

def generate_tone(frequency, duration, sample_rate, amplitude):
    """Generates a sine wave tone."""
    t = np.linspace(0., duration, int(sample_rate * duration), endpoint=False)
    return (amplitude * np.sin(2. * np.pi * frequency * t)).astype(np.int16)

def encode(input_path, output_path):
    """Encodes a file into a high-density MFSK WAV audio file."""
    print(f"Reading data from '{input_path}'...")
    try:
        with open(input_path, 'rb') as f:
            data = f.read()
    except FileNotFoundError:
        print(f"Error: Input file not found at '{input_path}'")
        return

    # Convert data to a stream of 4-bit nibbles (values 0-15)
    unpacked_bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))
    # Pad with zeros if not a multiple of 4
    if len(unpacked_bits) % 4 != 0:
        padding = 4 - (len(unpacked_bits) % 4)
        unpacked_bits = np.append(unpacked_bits, np.zeros(padding, dtype=np.uint8))

    # Reshape into 4-bit chunks and convert to integers
    nibbles = unpacked_bits.reshape(-1, 4)
    # Pack 4 bits into an integer value (0-15)
    values = (nibbles[:, 0] * 8 + nibbles[:, 1] * 4 + nibbles[:, 2] * 2 + nibbles[:, 3])

    print(f"Successfully read {len(data)} bytes ({len(values)} symbols).")

    print("Generating MFSK audio signal...")
    sync_header_tone = generate_tone(SYNC_HEADER_FREQ, SYNC_HEADER_DURATION, SAMPLE_RATE, AMPLITUDE)

    signal_chunks = [sync_header_tone]
    for value in values:
        freq = FREQUENCIES[value]
        tone = generate_tone(freq, SYMBOL_DURATION, SAMPLE_RATE, AMPLITUDE)
        signal_chunks.append(tone)

    full_signal = np.concatenate(signal_chunks)

    print(f"Writing audio to '{output_path}'...")
    wavfile.write(output_path, SAMPLE_RATE, full_signal)
    print(f"Encoding complete! Audio duration: {len(full_signal)/SAMPLE_RATE:.2f} seconds.")

def find_dominant_frequency(samples, sample_rate):
    """Finds the dominant frequency in a chunk of audio samples using FFT."""
    N = len(samples)
    if N == 0: return 0
    yf = np.fft.fft(samples)
    xf = np.fft.fftfreq(N, 1 / sample_rate)
    idx = np.argmax(np.abs(yf[0:N//2]))
    return xf[idx]

def decode(input_path, output_path):
    """Decodes a high-density MFSK WAV audio file back into a file."""
    print(f"Reading audio from '{input_path}'...")
    try:
        rate, audio_data = wavfile.read(input_path)
    except FileNotFoundError:
        print(f"Error: Input WAV file not found at '{input_path}'")
        return
    except ValueError:
        print(f"Error: Could not read WAV file. It might be corrupted or not a WAV file.")
        return

    if rate != SAMPLE_RATE:
        print(f"Warning: Audio sample rate ({rate}Hz) differs from expected ({SAMPLE_RATE}Hz).")

    if len(audio_data.shape) > 1: audio_data = audio_data.mean(axis=1)

    print("Searching for sync header...")
    sync_found = False
    start_index = -1
    chunk_size = SAMPLES_PER_SYNC_HEADER
    for i in range(0, len(audio_data) - chunk_size, chunk_size // 4):
        chunk = audio_data[i:i+chunk_size]
        freq = find_dominant_frequency(chunk, rate)
        if abs(freq - SYNC_HEADER_FREQ) < 20:
            start_index = i + chunk_size
            sync_found = True
            break

    if not sync_found:
        print("Error: Sync header not found. Cannot decode.")
        return

    print(f"Sync header found. Data starts at sample {start_index}.")

    data_audio = audio_data[start_index:]
    num_symbols = len(data_audio) // SAMPLES_PER_SYMBOL
    if num_symbols == 0:
        print("Error: Not enough audio data after sync header.")
        return

    print(f"Decoding {num_symbols} symbols...")

    decoded_values = []
    for i in range(num_symbols):
        chunk = data_audio[i * SAMPLES_PER_SYMBOL : (i + 1) * SAMPLES_PER_SYMBOL]
        dom_freq = find_dominant_frequency(chunk, rate)

        # Find the closest frequency in our MFSK set
        freq_errors = np.abs(FREQUENCIES - dom_freq)
        best_match_index = np.argmin(freq_errors)
        decoded_values.append(best_match_index)

    # Convert values (0-15) back to bits
    bit_stream = np.unpackbits(np.array(decoded_values, dtype=np.uint8)[:, np.newaxis], axis=1)
    # We only care about the lower 4 bits of each unpacked byte
    bits = bit_stream[:, 4:].flatten()

    # Pack bits into bytes
    byte_count = len(bits) // 8
    if byte_count == 0:
        print("Error: Decoded bits do not form a full byte.")
        return

    bits = bits[:byte_count * 8]
    decoded_bytes = np.packbits(bits)

    print(f"Writing {len(decoded_bytes)} bytes to '{output_path}'...")
    with open(output_path, 'wb') as f:
        f.write(decoded_bytes)

    print("Decoding complete!")

def main():
    parser = argparse.ArgumentParser(description="Encode/Decode files to/from high-density MFSK WAV audio.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    encode_parser = subparsers.add_parser("encode", help="Encode a file to a .wav file.")
    encode_parser.add_argument("input", type=str, help="Path to the input file.")
    encode_parser.add_argument("output", type=str, help="Path for the output .wav file.")

    decode_parser = subparsers.add_parser("decode", help="Decode a .wav file back to a file.")
    decode_parser.add_argument("input", type=str, help="Path to the input .wav file.")
    decode_parser.add_argument("output", type=str, help="Path for the reconstructed output file.")

    args = parser.parse_args()

    if args.command == "encode":
        encode(args.input, args.output)
    elif args.command == "decode":
        decode(args.input, args.output)

if __name__ == "__main__":
    main()

```
