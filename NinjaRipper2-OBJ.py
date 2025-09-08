import os
import sys
import struct
import argparse
from pathlib import Path

class NR2ObjConverter:
    def __init__(self):
        self.chunks = []
        self.nr_version = 0
        
    def read_nr_file(self, file_path):
        """Read and parse a NinjaRipper 2 .nr file based on the nrfile.py structure"""
        with open(file_path, 'rb') as f:
            data = f.read()
        
        # Check magic number
        magic = struct.unpack('<I', data[0:4])[0]
        if magic != 0x5049524E:  # 'NRIP' in little-endian
            raise ValueError("Not a valid NinjaRipper 2 file (missing NRIP magic)")
        
        # Get version
        self.nr_version = struct.unpack('<I', data[4:8])[0]
        if self.nr_version > 3:
            print(f"Warning: Unsupported version {self.nr_version}, trying to continue anyway")
        
        # Skip reserved fields
        pos = 16  # Start after header (magic(4) + version(4) + reserved(8))
        
        # Parse chunks
        while pos < len(data):
            if pos + 12 > len(data):
                break
                
            # Read chunk header (12 bytes)
            raw_size = struct.unpack('<I', data[pos:pos+4])[0]
            tag = struct.unpack('<I', data[pos+4:pos+8])[0]
            idx = struct.unpack('<I', data[pos+8:pos+12])[0]
            
            # Extract chunk data
            chunk_data = data[pos+12:pos+raw_size] if raw_size > 12 else b''
            
            # Store chunk info
            self.chunks.append((tag, idx, pos, raw_size, chunk_data))
            
            # Move to next chunk
            pos += raw_size
            
    def tag_to_string(self, tag):
        """Convert a tag integer to string representation"""
        return "".join([chr((tag >> (8 * i)) & 0xFF) for i in range(4)])
    
    def find_chunks(self, tag):
        """Find all chunks of a specific type"""
        return [chunk for chunk in self.chunks if chunk[0] == tag]
    
    def parse_vertex_data(self, vert_data):
        """Parse vertex data from VERT chunk based on nrfile.py structure"""
        # VERT chunk structure: vertex count (4 bytes), vertex size (4 bytes), then vertex data
        if len(vert_data) < 8:
            return []
            
        vertex_count = struct.unpack('<I', vert_data[0:4])[0]
        vertex_size = struct.unpack('<I', vert_data[4:8])[0]
        
        vertices = []
        pos = 8  # Start of vertex data
        
        for i in range(vertex_count):
            if pos + 12 > len(vert_data):
                break
                
            # Read position (3 floats, 12 bytes)
            x, y, z = struct.unpack('<fff', vert_data[pos:pos+12])
            vertices.append((x, y, z))
            pos += vertex_size  # Move to next vertex
            
        return vertices
    
    def parse_index_data(self, indx_data):
        """Parse index data from INDX chunk based on nrfile.py structure"""
        # INDX chunk structure: index count (4 bytes), topology (4 bytes), then index data
        if len(indx_data) < 8:
            return []
            
        index_count = struct.unpack('<I', indx_data[0:4])[0]
        
        indices = []
        pos = 8  # Start of index data
        
        for i in range(index_count):
            if pos + 4 > len(indx_data):
                break
                
            # Read index (4 bytes)
            index = struct.unpack('<I', indx_data[pos:pos+4])[0]
            indices.append(index)
            pos += 4
            
        return indices
    
    def convert_to_obj(self, nr_file_path, obj_file_path, use_world_space=True):
        """Convert .nr file to .obj file"""
        try:
            self.chunks = []  # Reset chunks for each conversion
            self.read_nr_file(nr_file_path)
            
            # Debug: print all found chunks
            print(f"Found {len(self.chunks)} chunks:")
            for i, (tag, idx, pos, size, data) in enumerate(self.chunks):
                tag_str = self.tag_to_string(tag)
                print(f"  {i}: {tag_str} (idx={idx}, pos={pos}, size={size})")
            
            # Find relevant chunks
            vert_chunks = self.find_chunks(0x54524556)  # 'VERT' in little-endian
            indx_chunks = self.find_chunks(0x58444E49)  # 'INDX' in little-endian
            
            print(f"Found {len(vert_chunks)} VERT chunks and {len(indx_chunks)} INDX chunks")
            
            if not vert_chunks or not indx_chunks:
                raise ValueError("No vertex or index data found in file")
            
            # Determine which vertex chunk to use
            # Typically first is local space, second is world space
            vert_chunk_idx = 1 if use_world_space and len(vert_chunks) > 1 else 0
            vert_chunk = vert_chunks[vert_chunk_idx]
            
            # Use the first index chunk (usually the same for both spaces)
            indx_chunk = indx_chunks[0]
            
            # Parse vertices and indices
            vertices = self.parse_vertex_data(vert_chunk[4])
            indices = self.parse_index_data(indx_chunk[4])
            
            # Write to OBJ file
            with open(obj_file_path, 'w') as obj_file:
                obj_file.write(f"# Converted from NinjaRipper 2 .nr file\n")
                obj_file.write(f"# Original file: {os.path.basename(nr_file_path)}\n")
                obj_file.write(f"# Vertex space: {'World' if use_world_space else 'Local'}\n\n")
                
                # Write vertices
                for v in vertices:
                    obj_file.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
                
                # Write faces (assuming triangles)
                obj_file.write("\n")
                for i in range(0, len(indices), 3):
                    if i + 2 < len(indices):
                        # OBJ indices are 1-based
                        obj_file.write(f"f {indices[i]+1} {indices[i+1]+1} {indices[i+2]+1}\n")
            
            print(f"Successfully converted {nr_file_path} to {obj_file_path}")
            print(f"Vertices: {len(vertices)}, Faces: {len(indices) // 3}")
            
        except Exception as e:
            print(f"Error converting file: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        return True

def main():
    # Check if files were dropped onto the script
    if len(sys.argv) > 1 and not sys.argv[1].startswith('-'):
        # Handle drag and drop
        for file_path in sys.argv[1:]:
            if os.path.isfile(file_path) and file_path.lower().endswith('.nr'):
                process_file(file_path)
            else:
                print(f"Skipping {file_path}: not a .nr file")
    else:
        # Handle command line arguments
        parser = argparse.ArgumentParser(description='Convert NinjaRipper 2 .nr files to Wavefront .obj format')
        parser.add_argument('input', nargs='?', help='Input .nr file or directory containing .nr files')
        parser.add_argument('-o', '--output', help='Output directory for .obj files')
        
        args = parser.parse_args()
        
        if not args.input:
            print("Please provide an input file or directory, or drag and drop .nr files onto this script.")
            return
        
        input_path = Path(args.input)
        output_dir = Path(args.output) if args.output else input_path.parent / "obj_output"
        output_dir.mkdir(exist_ok=True)
        
        # Process single file or directory
        if input_path.is_file() and input_path.suffix.lower() == '.nr':
            process_file(input_path, output_dir)
        elif input_path.is_dir():
            nr_files = list(input_path.glob('*.nr')) + list(input_path.glob('*.NR'))
            if not nr_files:
                print(f"No .nr files found in {input_path}")
                return
            
            print(f"Found {len(nr_files)} .nr files to convert")
            for nr_file in nr_files:
                process_file(nr_file, output_dir)
        else:
            print("Input must be a .nr file or a directory containing .nr files")
            return

def process_file(nr_file_path, output_dir=None):
    """Process a single .nr file and generate both Local and World space OBJ files"""
    if output_dir is None:
        output_dir = Path(nr_file_path).parent
    
    converter = NR2ObjConverter()
    
    # Generate Local space OBJ
    local_output = output_dir / f"{Path(nr_file_path).stem}_Local.obj"
    print(f"Converting {nr_file_path} to Local space...")
    if converter.convert_to_obj(nr_file_path, local_output, use_world_space=False):
        print("Local space conversion successful")
    else:
        print("Local space conversion failed")
    
    # Generate World space OBJ
    world_output = output_dir / f"{Path(nr_file_path).stem}_World.obj"
    print(f"Converting {nr_file_path} to World space...")
    if converter.convert_to_obj(nr_file_path, world_output, use_world_space=True):
        print("World space conversion successful")
    else:
        print("World space conversion failed")

if __name__ == "__main__":
    # If no arguments, show help
    if len(sys.argv) == 1:
        print("Drag and drop .nr files onto this script to convert them, or run from command line with arguments.")
        print("Usage: python nr2obj.py [input_file.nr] [-o output_directory]")
        input("Press Enter to exit...")
    else:
        main()
