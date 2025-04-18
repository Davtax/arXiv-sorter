from app.main import main
import tempfile

temp_dir = tempfile.TemporaryDirectory()

if __name__ == '__main__':
    try:  # Catch potential errors
        main(temp_dir)
    except Exception as e:
        print(f'An error occurred: {e}')

    temp_dir.cleanup()

    input('Press Enter to exit...')
