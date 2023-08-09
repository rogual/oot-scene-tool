import PIL.Image
import PIL.ImageFont
import PIL.ImageDraw


def render_text(text, out_size, path):
    """
    Render a text string to an image. Useful for title cards and other
    UI text.

    TODO: OOT has some text strings that have been compressed
    horizontally to fit a limited space (e.g. "Inside Jabu-Jabu's
    Belly"). The outlines on these are not compressed, though, they're
    nice and even all round. I can't find a good way to do this in
    PIL, so if this function needs to compress text, outlines will be
    ugly. We may have to ditch PIL to do this properly.
    """

    stroke_width = 2

    font_size = out_size[1]
    font = PIL.ImageFont.truetype('FOT-ChiaroStd-B.otf', font_size)

    text_size = font.getbbox(text, stroke_width=stroke_width)[2:]
    text_size = (
        text_size[0] + 2,
        text_size[1] + 2,
    )

    text_image = PIL.Image.new('RGBA', text_size)
    draw = PIL.ImageDraw.Draw(text_image)

    draw.text(
        (1, 1),
        text,
        font=font,
        stroke_width=stroke_width,
        fill=(255, 255, 255, 255),
        stroke_fill=(0, 0, 0, 255)
    )

    scale_x = min(1, out_size[0] / text_image.size[0])
    scale_y = min(1, out_size[1] / text_image.size[1])
    scale = min(scale_x, scale_y)

    text_image = text_image.resize(
        (int(scale * text_image.size[0]),
         int(scale * text_image.size[1])),
        resample=PIL.Image.LANCZOS
    )

    out_image = PIL.Image.new('RGBA', out_size)
    out_image.paste(
        text_image, (
            (out_image.size[0] - text_image.size[0]) // 2,
            (out_image.size[1] - text_image.size[1]) // 2
        )
    )

    out_image.save(path)



if __name__ == '__main__':
    render_text('Spoopy Temple', (96, 16), 'text.png')


    
