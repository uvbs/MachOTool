from range import Range
from bytes import Bytes


class ByteRange(Range):
    def __init__(self, offset, length, data=None, parent=None):
        assert isinstance(parent, ByteRange) or parent is None
        if parent is None:
            assert offset == 0
        super(ByteRange, self).__init__(offset, length)
        self.subranges = list()
        self.parent = parent
        self.data = data

    def __repr__(self):
        out = '<BytesRange:%d-%d' % (self.start, self.stop)
        if len(self.subranges) == 0:
            out += '>'
        else:
            separator = ':'
            for sr in self.subranges:
                out += separator + '%d-%d' % (sr.start, sr.stop)
                if separator != ',':
                    separator = ','
        return out

    def add_subrange(self, offset, length, data=None):
        if offset < 0 or length < 0 or (offset + length > self.stop):
            raise ValueError()
        new_subrange = ByteRange(offset, offset + length, data, self)

        if len(self.subranges) == 0 or new_subrange > self.subranges[-1]:
            # Add new subrange to the end
            self.subranges.append(new_subrange)
        elif new_subrange < self.subranges[0]:
            self.subranges.insert(0, new_subrange)
        else:
            left_idx = 0
            right_idx = len(self.subranges) - 1

            while right_idx - left_idx > 1:
                mid_idx = (left_idx + right_idx) / 2
                mid = self.subranges[mid_idx].start
                if mid < new_subrange.start:
                    left_idx = mid_idx
                elif mid > new_subrange.start:
                    right_idx = mid_idx
                else:
                    raise ValueError('New range overlaps with an existing range.')
            if (self.subranges[left_idx] < new_subrange) and (new_subrange < self.subranges[right_idx]):
                self.subranges.insert(right_idx, new_subrange)
            else:
                raise ValueError('New range overlaps with an existing range.')

        return new_subrange

    def insert_subrange(self, offset, length, data=None):
        """
        Unlike add_subrange() which appends a new subrange on top of current range, this method
        inserts a subrange between this byte range and existing subranges that are covered by
        this new subrange. It can be used for grouping for example.
        """
        # Make sure that there is no subrange that spans the boundary (start and / or stop).
        subsubranges = list()
        tmp_range = Range(offset, offset + length)
        for sr in self.subranges:
            if sr < tmp_range:
                continue
            if sr > tmp_range:
                break  # we have gone past anything that may overlap. no need to continue
            if sr in tmp_range:
                subsubranges.append(sr)
            else:
                raise ValueError('subrange %d-%d spans boundary' % (sr.start, sr.stop))

        # Remove all subranges that belong to the new subrange
        for ssr in subsubranges:
            self.subranges.remove(ssr)

        # Add the new subrange
        new_sr = self.add_subrange(offset, length, data)

        # Put all the removed subranges back
        for ssr in subsubranges:
            new_ssr = new_sr.add_subrange(ssr.start - offset, len(ssr), data=ssr.data)
            new_ssr.subranges = ssr.subranges

        return new_sr

    def abs_start(self):
        start = self.start
        parent = self.parent
        while parent is not None:
            start += parent.start
            parent = parent.parent
        return start

    def abs_end(self):
        return self.abs_start() + len(self)

    def abs_range(self, start=None, stop=None):
        if start is None:
            start = 0
        if stop is None:
            stop = len(self)

        abs_start = self.abs_start()
        start += abs_start
        stop += abs_start

        return start, stop

    def does_partition(self):
        if len(self.subranges) == 0:
            return True
        cur = 0
        for sr in self.subranges:
            if cur != sr.start:
                return False  # there is a gap
            if not sr.does_partition():
                return False
            cur = sr.stop
        result = cur == len(self)  # the last subrange needs to go all the way to the end
        if not result:
            pass
        return result

    def bytes(self, start=None, stop=None):
        assert (start is None) or isinstance(start, int)
        assert (stop is None) or isinstance(stop, int)

        br = self
        while br.parent is not None:
            br = br.parent
        if br.data is None:
            return None
        assert isinstance(br.data, Bytes)
        start, stop = self.abs_range(start, stop)
        return br.data.range(start, stop)

    def last_subrange_stop(self):
        if len(self.subranges) == 0:
            return self.start
        return self.subranges[-1].stop

    def iterate_leaves(self, callback, start=0, level=0):
        assert callable(callback)
        if len(self.subranges) == 0:
            result = callback(self, start, start + len(self), level)
            return [result]
        results = list()
        for sr in self.subranges:
            results += sr.iterate_leaves(callback, start + sr.start, level + 1)
        return results

    def iterate(self, callback, start=0, level=0):
        this_result = callback(self, start, start + len(self), level)
        results = list()
        if this_result is not None:
            results.append(this_result)
        for sr in self.subranges:
            results += sr.iterate(callback, start + sr.start, level + 1)
        return results

    def scan_gap(self, callback):
        assert callable(callback)
        if len(self.subranges) > 0:
            current = 0
            for sr in self.subranges:
                gap = sr.start - current
                if gap > 0:
                    # There is a gap in front
                    data = callback(current, current + gap)
                    self.add_subrange(current, gap, data=data)
                current = sr.stop
            gap = self.stop - (self.start + current)
            if gap > 0:
                data = callback(current, current + gap)
                self.add_subrange(current, gap, data=data)
