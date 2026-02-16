import numpy as np
import threading
import time

class RingBuffer:
    def __init__(self, size_samples: int, dtype=np.float32):
        self.size_samples = size_samples
        self.dtype = dtype
        self.buffer = np.zeros(size_samples, dtype=dtype)
        self.write_index = 0
        self.lock = threading.Lock()
        self.full = False 

    def write(self, data: np.ndarray):
        """Append data to the ring buffer."""
        n_samples = len(data)
        if n_samples == 0:
            return

        with self.lock:
            if n_samples > self.size_samples:
                # If data is larger than buffer, just write the last part
                self.buffer[:] = data[-self.size_samples:]
                self.write_index = 0 
                self.full = True
                return

            remaining_space = self.size_samples - self.write_index
            
            if n_samples <= remaining_space:
                self.buffer[self.write_index : self.write_index + n_samples] = data
                self.write_index += n_samples
            else:
                # Wrap around
                self.buffer[self.write_index : self.size_samples] = data[:remaining_space]
                second_part_len = n_samples - remaining_space
                self.buffer[0 : second_part_len] = data[remaining_space:]
                self.write_index = second_part_len
                self.full = True
            
            if self.write_index == self.size_samples:
                self.write_index = 0
                self.full = True

    def get_last_n_samples(self, n_samples: int) -> np.ndarray:
        """Get the most recent n_samples from the buffer."""
        with self.lock:
            if self.full:
                # Buffer is full, data is wrapped
                # Current write_index is the "head" (oldest data is at write_index, newest at write_index-1)
                # But we want the *last* N samples, which are logically before write_index.
                
                if n_samples >= self.size_samples:
                    # Return entire buffer, rotated correctly
                    return np.concatenate((self.buffer[self.write_index:], self.buffer[:self.write_index]))

                # We need samples ending at write_index-1
                end_idx = self.write_index
                start_idx = end_idx - n_samples
                
                if start_idx >= 0:
                     return self.buffer[start_idx : end_idx].copy()
                else:
                    # Wrap around
                    # start_idx is negative, e.g. -5. 
                    # We need last 5 samples. Part 1: buffer[size-5 : size], Part 2: buffer[0 : end_idx]
                    part1 = self.buffer[start_idx:] # indices like -5: 
                    part2 = self.buffer[:end_idx]
                    return np.concatenate((part1, part2))

            else:
                # Buffer not full yet
                if n_samples > self.write_index:
                    # Requesting more than available, return what we have (or should we pad?)
                    # For now return available
                    return self.buffer[:self.write_index].copy()
                
                end_idx = self.write_index
                return self.buffer[end_idx - n_samples : end_idx].copy()

    def get_all(self) -> np.ndarray:
        """Get all valid data in the buffer."""
        with self.lock:
            if not self.full:
                return self.buffer[:self.write_index].copy()
            else:
                return np.concatenate((self.buffer[self.write_index:], self.buffer[:self.write_index]))

